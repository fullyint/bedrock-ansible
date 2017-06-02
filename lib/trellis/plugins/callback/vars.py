from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from os import listdir
from os.path import basename, isfile, join
import re
import sys
import ConfigParser

from __main__ import cli
from ansible import constants as C
from ansible.config.manager import find_ini_config_file
from ansible.module_utils.six import iteritems
from ansible.errors import AnsibleError
from ansible.parsing.yaml.objects import AnsibleMapping, AnsibleSequence, AnsibleUnicode
from ansible.playbook.play_context import PlayContext
from ansible.playbook.task import Task
from ansible.plugins.callback import CallbackBase
from ansible.plugins.filter.core import combine
from ansible.template import Templar
from ansible.utils.vars import combine_vars, load_extra_vars
from ansible.utils.unsafe_proxy import AnsibleUnsafeText
from itertools import chain


class CallbackModule(CallbackBase):
    ''' Creates and modifies play and host variables '''

    CALLBACK_VERSION = 2.0
    CALLBACK_NAME = 'vars'

    def __init__(self):
        self._options = cli.options if cli else None

    def raw_triage(self, key_string, item, patterns):
        # process dict values
        if isinstance(item, (AnsibleMapping, dict)):
            return AnsibleMapping(dict((key,self.raw_triage('.'.join([key_string, key]), value, patterns)) for key,value in item.iteritems()))

        # process list values
        elif isinstance(item, (AnsibleSequence, list)):
            return AnsibleSequence([self.raw_triage('.'.join([key_string, str(i)]), value, patterns) for i,value in enumerate(item)])

        # wrap values if they match raw_vars pattern
        elif isinstance(item, (AnsibleUnicode, AnsibleUnsafeText)):
            match = next((pattern for pattern in patterns if re.match(pattern, key_string)), None)
            return AnsibleUnicode(''.join(['{% raw %}', item, '{% endraw %}'])) if not item.startswith(('{% raw', '{%raw')) and match else item

    def raw_vars(self, play, host, hostvars):
        if 'raw_vars' not in hostvars:
            return

        raw_vars = Templar(variables=hostvars, loader=play._loader).template(hostvars['raw_vars'])
        if not isinstance(raw_vars, list):
            raise AnsibleError('The `raw_vars` variable must be defined as a list.')

        patterns = [re.sub(r'\*', '(.)*', re.sub(r'\.', '\.', var)) for var in raw_vars if var.split('.')[0] in hostvars]
        keys = set(pattern.split('\.')[0] for pattern in patterns)
        for key in keys:
            if key in play.vars:
                play.vars[key] = self.raw_triage(key, play.vars[key], patterns)
            elif key in hostvars:
                host.vars[key] = self.raw_triage(key, hostvars[key], patterns)

    def cli_options(self):
        options = []

        strings = {
            '--connection': 'connection',
            '--private-key': 'private_key_file',
            '--ssh-common-args': 'ssh_common_args',
            '--ssh-extra-args': 'ssh_extra_args',
            '--timeout': 'timeout',
            '--vault-password-file': 'vault_password_file',
            }

        for option,value in strings.iteritems():
            if getattr(self._options, value, False):
                options.append("{0}='{1}'".format(option, str(getattr(self._options, value))))

        for inventory in getattr(self._options, 'inventory'):
            options.append("--inventory='{}'".format(str(inventory)))

        if getattr(self._options, 'ask_vault_pass', False):
            options.append('--ask-vault-pass')

        return ' '.join(options)

    def darwin_without_passlib(self):
        if not sys.platform.startswith('darwin'):
            return False

        try:
            import passlib.hash
            return False
        except:
            return True

    def get_project_vars(self, play, hostvars):
        project_path = Templar(variables=hostvars, loader=play._loader).template(hostvars['project_path'])
        vars = {}

        for path in ['{}/vars/all'.format(project_path), '{}/vars/{}'.format(project_path, hostvars['env'])]:
            files = [f for f in listdir(path) if isfile(join(path, f))]
            for file in files:
                _vars = play._loader.load_from_file(join(path, file))

                if _vars is not None:
                    vars = combine_vars(vars, _vars)

        return vars

    def get_raw_vars(self, keys, patterns, key, value):
        if key in keys and value != {}:
            return self.raw_triage(key, value, patterns)
        else:
            return value

    # simple recreation of lib/trellis/plugins/lookup/combine_for_host.py
    # didn't do a `lookup('combine_for_host', ...)` because Ansible's lookups template all vars, in this case before all vars are available.
    # Specifically, wp_home uses `site_hosts_canonical | first` which has/had a default to `site` if
    # `site_hosts` hadn't yet been created, but `site` lacks the `.com` etc. making `wp_home` incorrect.
    # tl;dr we need this combine_for_host to NOT template the var values yet.
    def combine_for_host(self, host, vars, lookup):
        dicts_to_combine = [{}]
        for var_subset in vars:
            for host_pattern,subset_vars in var_subset.iteritems():
                if host in lookup('inventory_hostnames', host_pattern, wantlist=True):
                    dicts_to_combine.append(subset_vars)

        return combine(*dicts_to_combine, recursive=True)

    def get_merged_var(self, play, hostvars, key):
        # prepare for raw_vars processing
        raw_vars = Templar(variables=hostvars, loader=play._loader).template(hostvars['raw_vars'])
        patterns = [re.sub(r'\*', '(.)*', re.sub(r'\.', '\.', var)) for var in raw_vars if var.split('.')[0] in hostvars]
        keys = set(pattern.split('\.')[0] for pattern in patterns)

        # retrieve values for vars to be merged
        lookup = Templar(variables=hostvars, loader=play._loader)._lookup
        host = hostvars['inventory_hostname']
        vars_by_context = {}

        for var_context in ['_global', '_for_project']:
            if key.startswith('site_vars'):
                _vars = self.combine_for_host(host, hostvars.get(key + var_context, {}), lookup)
            else:
                _vars = hostvars.get(key + var_context, {})

            vars_by_context[var_context] = self.get_raw_vars(keys, patterns, key + var_context, _vars)

        # loop through sites and merge vars
        vars_merged = {}

        for site,vars_for_site in hostvars.get(key, {}).iteritems():
            if key.startswith('site_vars'):
                vars_for_site = self.combine_for_host(host, vars_for_site, lookup)

            vars_for_site = self.get_raw_vars(keys, patterns, key, vars_for_site)
            dicts_to_combine = [vars_by_context['_global'], vars_by_context['_for_project'], vars_for_site]
            vars_merged[site] = combine(*dicts_to_combine, recursive=True)

        return vars_merged

    def load_site_vars(self, play, host, hostvars):
        # identify play context -- dynamic_hosts or not?
        groups = [group.name for group in host.groups]
        dynamic_hosts = 'dynamic_hosts' in groups

        if dynamic_hosts:
            current_site = hostvars['site']

        # load vault_site_vars_merged into host.vars
        vault_site_vars_merged = {}
        for project in hostvars.get('child_projects', [hostvars.get('parent_project', hostvars['project'])]):
            _project_vars = self.get_project_vars(play, combine_vars(hostvars, {'project':project}))
            _hostvars = combine_vars(hostvars, _project_vars)
            vault_site_vars_merged = combine_vars(vault_site_vars_merged, self.get_merged_var(play, _hostvars, 'vault_site_vars'))
        host.vars['vault_site_vars_merged'] = vault_site_vars_merged

        # load vault_site_vars_merged for site into the hostvars used in creating site_vars_merged below
        if dynamic_hosts:
            hostvars = combine_vars(hostvars, vault_site_vars_merged[current_site])
        else:
            for key in list(set(chain.from_iterable([item.keys() for item in vault_site_vars_merged.values()]))):
                hostvars[key] = hostvars.get(key, 'unavailable')
                host.vars[key] = hostvars.get(key, 'unavailable')
            hostvars['site'] = hostvars.get('site', 'unavailable')
            host.vars['site'] = hostvars.get('site', 'unavailable')

        # load site_vars_merged into host.vars
        site_vars_merged = {}
        for project in hostvars.get('child_projects', [hostvars.get('parent_project', hostvars['project'])]):
            _project_vars = self.get_project_vars(play, combine_vars(hostvars, {'project':project}))
            _hostvars = combine_vars(hostvars, _project_vars)
            site_vars_merged = combine_vars(site_vars_merged, self.get_merged_var(play, _hostvars, 'site_vars'))
        host.vars['site_vars_merged'] = site_vars_merged

        # if dynamic_hosts, load site_vars_merged and vault_site_vars_merged for current_site into top level vars
        if dynamic_hosts:
            host.vars = combine_vars(host.vars, vault_site_vars_merged[current_site])
            host.vars = combine_vars(host.vars, site_vars_merged[current_site])

    def v2_playbook_on_start(self, playbook):
        options = lambda: None
        p = ConfigParser.ConfigParser()
        config_file = find_ini_config_file()
        p.read(config_file)
        options.extra_vars = C.get_config(p, 'trellis', 'trellis_extra_vars', 'TRELLIS_EXTRA_VARS', '').split(' ')
        trellis_extra_vars = load_extra_vars(playbook._loader, options)

        trellis_env_vars = {}
        for env_var in ['trellis_projects', 'trellis_sites', 'trellis_env']:
            value = C.get_config(p, 'trellis', env_var, env_var.upper(), 'all' if env_var == 'trellis_projects' else None)
            if value is not None:
                trellis_env_vars[env_var.replace('trellis_','')] = value

        # force env = 'development' for dev.yml playbook
        if basename(playbook._file_name) == 'dev.yml':
            trellis_env_vars['env'] = 'development'

        for play in playbook.get_plays():
            play.vars = combine_vars(play.vars, trellis_extra_vars)
            play.vars = combine_vars(play.vars, trellis_env_vars)

            # check for `env` var defined
            cli_extra_vars = load_extra_vars(play._loader, self._options)
            if 'env' not in combine_vars(play.vars, cli_extra_vars) and basename(playbook._file_name) != 'dev.yml':
                extra_vars_command = '"site=<domain> env=<environment>"' if basename(playbook._file_name) == 'deploy.yml' else 'env=<environment>'
                need_env_msg = ('Use `-e` to define `env`:\nansible-playbook {} -e {}\n'.format(basename(playbook._file_name), extra_vars_command))
                sys.stderr.write(need_env_msg)
                sys.exit(1)

    def v2_playbook_on_play_start(self, play):
        env = play.get_variable_manager().get_vars(play=play).get('env', '')
        env_group = next((group for key,group in play.get_variable_manager()._inventory.groups.iteritems() if key == env), False)
        if env_group:
            env_group.set_priority(20)

        for host in play.get_variable_manager()._inventory.list_hosts(play.hosts[0]):
            # it should be ok to remove dummy Task() once minimum required Ansible >= 2.4.2
            hostvars = play.get_variable_manager().get_vars(play=play, host=host, task=Task())
            project_vars = self.get_project_vars(play, hostvars)
            host.vars = combine_vars(host.vars, project_vars)
            self.raw_vars(play, host, combine_vars(hostvars, project_vars))
            self.load_site_vars(play, host, combine_vars(hostvars, project_vars))
            host.vars['ssh_args_default'] = PlayContext(play=play, options=self._options)._ssh_args.default
            host.vars['cli_options'] = self.cli_options()
            host.vars['cli_ask_pass'] = getattr(self._options, 'ask_pass', False)
            host.vars['cli_ask_become_pass'] = getattr(self._options, 'become_ask_pass', False)
            host.vars['darwin_without_passlib'] = self.darwin_without_passlib()
