#!/usr/bin/env python

'''
Dynamic inventory for Ansible with Trellis
==========================================
Props: Jeff Geerling https://www.jeffgeerling.com/blog/creating-custom-dynamic-inventories-ansible

Reads from a hosts/hosts.yml file (no Jinja2) with the following construction:

  # required: `projects` dict
  # -------------------------------

  projects:                            # all projects should be defined in the required `projects` dict

    simple_project:                    # minimal project example -- example values
      web:                             # ---------------------------------------------------
        production: 11.11.11.11
        staging: 22.22.22.22
        development: 192.168.50.5

                                       # minimum required structure for a project (sub) dict
                                       # ---------------------------------------------------
    <name>:                            # project name
      <type>:                          # hosts' type such as `web` or `db`
        <env>: 11.11.11.11             # hosts' environment such as `production`
                                       # host names/IPs may only appear in <env>; <env> may only appear in <type>


                                       # complex example with more explanation
                                       # ---------------------------------------------------
    complex_project:                   # project name serves as group name and value of `project` variable for group
      vars:                            # optional: vars for project group, but better to use projects/<project-name>/vars
        group_var_for_project: foo     # example variable for the project's group_vars
        vagrant_private_key_file: path # optional: set path to private SSH key to avoid processing time of auto-detecting path
      parents:                         # optional: list of additional groups of which this project group is a child
        - some_meta_group              # parent groups listed here will be created if they do not already exist
      web:                             # required: group name indicating type for hosts (e.g., `web` or `db`)
        production:                    # required: environment group name (e.g., `production`)
          - 22.22.22.22                # host list item may be simple string value, interpreted as ansible_host
                                       # or host list item may be a dict...
          - name: myhost               # optional: host name/alias default is <project_name>_<type*>_<env>_<ansible_host*>
            ansible_host: 33.33.33.33  #   (default name includes <type> and <ansible_host> only if there are multiples of each)
            groups:                    # optional: list of additional groups to which this host belongs
              - nyc1                   # example: group indicating data center or availability zone
            foo: bar                   # optional: additional variables may be defined for host (no `vars` key needed)
        staging: 44.44.44.44           # <env> may have value of a simple string indicating ansible_host
        development:                   # note: when Ansible is running on Vagrant, `ansible_connection` is forced to `local`
          - ansible_host: 192.168.50.6
            vagrant_primary: true      # optional: https://www.vagrantup.com/docs/multi-machine/#specifying-a-primary-machine
            vagrant_autostart: true    # optional: https://www.vagrantup.com/docs/multi-machine/#autostart-machines


  # optional: `groups` dict
  # -------------------------------
  # Additional functionality for assigning groups (augments `parents` and `groups` options in `projects` dict above)
  # All three subkeys are optional: `hosts` list, `children` list, `vars` dict

  groups:                              # additional groups may be defined in an optional `groups` dict

    multisite:                         # group name, e.g., perhaps useful for `multisite` group to have specific group_vars
      hosts:                           # optional: list of hosts in this group
        - simple_project_production    # example of default hostname generated from `projects` above
        - myhost                       # example of `name` specified for host in `complext_project` in `projects` above
      children:                        # optional: list of child groups
        - project_a                    # child groups listed here will be created (empty) if they do not already exist
        - project_b
      vars:                            # optional: vars for group, but consider creating vars files in group_vars/<group-name>
        bar: baz

    az_west:                           # example of grouping hosts by availability zone or data center
      hosts:
        - westhost1
        - westhost2

    cloud_provider_a:                  # example of creating a parent group for the `az_west` group created here in `groups`
      children:
        - az_west

    active:                            # example parent group for the purpose of loading multiple projects on a single VM
      children:
        - project1
        - project2
        - project3
      web:                             # required: group name indicating host type (e.g., `web` or `db`)
        development:                   # required: group name indicating environment (e.g., `development`)
          - ansible_host: 192.168.50.9 # the VM will be accessible at the specified `ansible_host`
            base_project: project2     # the VM will use general configs from the specified `base_project`
            vagrant_primary: false     # each WordPress site will use its own configs from `site_vars.yml`
            vagrant_autostart: true
            vagrant_private_key_file: path

    ecommerce:                         # another example parent group for loading multiple projects on a single VM
      children:
        - ecommerce_project_1
        - ecommerce_project_2
      web:
        development: 192.168.50.10     # example of `development` being just a string (vs. list as in example above)
                                       # `base_project` will default to first project in group (alphabetically)

    all-projects:                      # the `all-projects` group will be created automatically
      # children: DO NOT DEFINE        # children for the `all-projects` group will be added automatically
      web:
        development: 192.168.50.11     # optionally specify IP, making the `all-projects` group available as a multi-project VM

'''

import sys
import argparse
import yaml

from ansible.module_utils.six import iteritems, string_types
from ansible.utils.vars import combine_vars

try:
    import json
except ImportError:
    import simplejson as json


class TrellisInventory(object):

    def __init__(self):
        self.inventory = {}
        self.read_cli_args()

        # Called with `--list`.
        if self.args.list:
            self.inventory = self.build_inventory()
        # Called with `--host [hostname]`.
        elif self.args.host:
            # Not implemented, since we return _meta info `--list`.
            self.inventory = self.empty_inventory()
        # If no groups or vars are present, return an empty inventory.
        else:
            self.inventory = self.empty_inventory()

        print json.dumps(self.inventory);

    def build_inventory(self):
        # TODO: check if file exists, maybe make the read try/except
        with open('hosts/hosts.yml', 'r') as hosts_file:
            data_from_file = yaml.load(hosts_file)

        data = {}
        hosts = {}
        duplicate_hosts = []

        for project,host_types in data_from_file['projects'].iteritems():
            data[project] = {'hosts': [], 'vars': {'project': project}}

            # TODO: change to more universal var names for this loop?
            for host_type,envs in host_types.iteritems():
                # add group vars -- fudging on var names :(
                if host_type == 'vars':
                    data[project]['vars'] = envs
                    data[project]['vars']['project'] = project
                    continue

                # assign project to parent groups -- fudging on var names :(
                elif host_type == 'parents':
                    for parent in envs:
                        if parent not in data:
                            data[parent] = {'children': []}
                        data[parent]['children'] = list(set(data[parent].get('children', []) + [parent]))
                    continue

                # finally deal with actual host_type groups and env groups
                host_type_name = '_{}'.format(host_type) if len(set([type for type in host_types if type not in ['vars','parents']])) > 1 else ''

                if host_type not in data:
                    data[host_type] = {'hosts': []}

                for env,item in envs.iteritems():
                    hostname = '{}{}_{}'.format(project, host_type_name, env)

                    if env not in data:
                        data[env] = {'hosts': []}

                    def add_to_standard_groups(host):
                        for group in [project, host_type, env]:
                            if host not in data[group]['hosts']:
                                data[group]['hosts'].append(host)
                            else:
                                duplicate_hosts.append(host)

                    # if value of env item is string
                    # example:
                    #   web:
                    #     production: 12.34.56.78
                    if isinstance(item, string_types):
                        add_to_standard_groups(hostname)

                        # assign ansible_host value
                        hosts[hostname] = {'ansible_host': item}

                    # if value of env item is list
                    elif isinstance(item, list):
                        for host_item in item:

                            # if list item (host) is simple string
                            # example:
                            #   web:
                            #     production:
                            #       - 12.34.56.78
                            if isinstance(host_item, string_types):
                                # append ansible_host info to hostname if multiple hosts for this env
                                if len(item) > 1:
                                    hostname = '{}_{}'.format(hostname, host_item)

                                add_to_standard_groups(hostname)

                                # assign ansible_host value
                                hosts[hostname] = {'ansible_host': host_item}

                            # if list item (host) is a dict
                            # example:
                            #   web:
                            #     production:
                            #       - name: some_alias
                            #         ansible_host: 12.34.56.78
                            #         some_host_var: foo
                            elif isinstance(host_item, dict):
                                if 'name' in host_item:
                                    hostname = host_item.pop('name')
                                elif len(item) > 1:
                                    hostname = '{}_{}'.format(hostname, host_item['ansible_host'])

                                add_to_standard_groups(hostname)

                                # assign host to additional groups
                                for group in host_item.pop('groups', []):
                                    if group not in data:
                                        data[group] = {'hosts': []}
                                    if hostname not in data[group]['hosts']:
                                        data[group]['hosts'].append(hostname)

                                # add any remaining vars from the host item dict
                                hosts[hostname] = host_item

        if duplicate_hosts:
            err_msg = ('\nThe following hosts are created multiple times in hosts/hosts.yml:\n'
                       '  - {}\n'
                       'Please adjust hosts/hosts.yml to create each host only once.'
                       .format('\n  - '.join(set(duplicate_hosts)))
                      )
            sys.stderr.write(err_msg)
            sys.exit(1)

        # process the `groups` dict from hosts.yml
        for group,group_data in data_from_file.get('groups', {}).iteritems():
            if group not in data:
                data[group] = {}

            _standard_attrs = ['hosts','children','vars']
            standard_attrs = [attr for attr in _standard_attrs if attr in group_data]
            for attr in standard_attrs:
                if attr not in data[group]:
                    data[group][attr] = {} if attr == 'vars' else []

                # augment existing 'hosts', 'children', or 'vars'
                if attr == 'vars':
                    data[group][attr] = combine_vars(data[group][attr], group_data[attr])
                else:
                    data[group][attr] = list(set(data[group][attr] + group_data[attr]))

                # add child groups that do not yet exist
                if attr == 'children':
                    children_to_add = [child for child in group_data['children'] if child not in data]
                    for child in children_to_add:
                        data[child] = {'hosts': []}

            # hosts.yml allows extra attributes for `groups`, typically used for Vagrant VMs
            extra_attrs = [attr for attr in group_data if attr not in _standard_attrs]
            for attr in extra_attrs:
                data[group][attr] = group_data[attr]

        # create all-projects group and its children
        data['all-projects'] = combine_vars(data.get('all-projects', {}), {'children':data_from_file['projects'].keys() })

        data['_meta'] = {'hostvars': hosts}
        return data

    # Empty inventory for testing.
    def empty_inventory(self):
        return {'_meta': {'hostvars': {}}}

    # Read the command line args passed to the script.
    def read_cli_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--list', action = 'store_true')
        parser.add_argument('--host', action = 'store')
        self.args = parser.parse_args()

# Get the inventory.
TrellisInventory()
