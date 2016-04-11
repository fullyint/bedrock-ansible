from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible import __version__
from ansible.errors import AnsibleError

if __version__.startswith('1'):
    raise AnsibleError('Trellis no longer supports Ansible 1.x. Please upgrade to Ansible 2.x.')

from ansible.parsing.dataloader import DataLoader
from ansible.plugins.filter.mathstuff import difference


class VarsModule(object):
    ''' Creates and modifies host variables '''

    def __init__(self, inventory):
        self.inventory = inventory
        self.inventory_basedir = inventory.basedir()

    # Wrap salts and keys variables in {% raw %} to prevent jinja templating errors
    def wrap_salts_in_raw(self, host, hostvars):
        if 'vault_wordpress_sites' in hostvars:
            for name, site in hostvars['vault_wordpress_sites'].iteritems():
                for key, value in site['env'].iteritems():
                    if key.endswith(('_key', '_salt')) and not value.startswith(('{% raw', '{%raw')):
                        hostvars['vault_wordpress_sites'][name]['env'][key] = ''.join(['{% raw %}', value, '{% endraw %}'])
            host.vars['vault_wordpress_sites'] = hostvars['vault_wordpress_sites']

    def sites(self, hostvars):
        if 'site' in hostvars:
            sitename = hostvars['site']
            if sitename in hostvars['wordpress_sites']:
                sites = {sitename: hostvars['wordpress_sites'][sitename]}
            else:
                sites = {}
        else:
            sites = hostvars['wordpress_sites']
        return sites

    def get_host_vars(self, host, vault_password=None):
        loader = DataLoader()
        hostvars = self.inventory._variable_manager.get_vars(loader=loader, host=host)
        self.wrap_salts_in_raw(host, hostvars)
        host.vars['unvaulted_sites'] = difference(self.sites(hostvars).keys(), hostvars['vault_wordpress_sites'].keys())
        return {}
