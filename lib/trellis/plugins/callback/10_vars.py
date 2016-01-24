# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os.path
import re
import sys

from ansible.compat.six import iteritems
from ansible.parsing.vault import VaultLib
from ansible.plugins.callback import CallbackBase
from ansible.plugins.filter.mathstuff import difference
from ansible.utils.unicode import to_unicode

try:
    from trellis.plugins.callback import TrellisCallbackBase
except ImportError:
    if sys.path.append(os.path.join(os.getcwd(), 'lib')) in sys.path: raise
    sys.path.append(sys.path.append(os.path.join(os.getcwd(), 'lib')))
    from trellis.plugins.callback import TrellisCallbackBase


class CallbackModule(TrellisCallbackBase, CallbackBase):
    ''' Creates custom variables accessible in Ansible playbooks '''

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = '10_vars'

    def __init__(self):

        super(CallbackModule, self).__init__()

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

    def db_name_dups(self, hostvars):
        sites = self.sites(hostvars)
        db_names = []
        for site in sites.values():
            db_names.append(site['env']['db_name'])
        # Get list of duplicate db names -- http://stackoverflow.com/a/9836685
        seen = set()
        seen2 = set()
        seen_add = seen.add
        seen2_add = seen2.add
        for name in db_names:
            if name in seen:
                seen2_add(name)
            else:
                seen_add(name)
        selected_sites = {}
        for key, site in sites.iteritems():
            if site['env']['db_name'] in seen2:
                selected_sites[key] = {'env': {'db_name': ''.join(['C_ERROR', site['env']['db_name'], 'C_ERROR'])}}
        return selected_sites

    def site_hosts_with_protocol(self, hostvars):
        sites = self.sites(hostvars)
        selected_sites = {}
        for key, site in sites.iteritems():
            for host in site['site_hosts']:
                if host.startswith('http'):
                    if key not in selected_sites:
                        selected_sites[key] = {'site_hosts': []}
                    selected_sites[key]['site_hosts'].append(re.sub(r'(https?://)', r'C_ERROR\1C_ERROR', host))
        return selected_sites

    def wp_env_no_protocol(self, hostvars):
        sites = ((k,v) for k,v in self.sites(hostvars).items() if 'env' in v)
        selected_sites = {}
        for key, site in sites:
            for var in ['wp_home', 'wp_siteurl']:
                if var in site['env'] and not site['env'][var].startswith('http'):
                    if key not in selected_sites:
                        selected_sites[key] = {'env': {}}
                    selected_sites[key]['env'][var] = ''.join(['C_ERROR', site['env'][var], 'C_ERROR'])
        return selected_sites

    def no_site_hosts_in_wp_env(self, hostvars):
        sites = ((k,v) for k,v in self.sites(hostvars).iteritems() if 'env' in v)
        selected_sites = {}
        for key, site in sites:
            for host in site['site_hosts']:
                pattern = r'https?://{0}.*'.format(host)
                error_host = ''.join(['C_ERROR', host, 'C_ERROR'])
                for var in ['wp_home', 'wp_siteurl']:
                    if var in site['env'] and not re.match(pattern, site['env'][var]):
                        if key not in selected_sites:
                            selected_sites[key] = {'site_hosts': [], 'env': {}}
                        if error_host not in selected_sites[key]['site_hosts']:
                            selected_sites[key]['site_hosts'].append(error_host)
                        selected_sites[key]['env'][var] = ''.join(['C_ERROR', site['env'][var], 'C_ERROR'])
        return selected_sites

    def unencrypted_vault_files(self, hostvars):
        if 'vault_files' not in hostvars:
            return []
        vault = VaultLib(password=None)
        cwd = os.getcwd()
        unencrypted = []
        for file in hostvars['vault_files']:
            filepath = os.path.join(cwd, file)
            if os.path.isfile(filepath):
                with open(filepath, 'rb') as f:
                    data = f.read()
                    if not vault.is_encrypted(data):
                        unencrypted.append(file)
        return unencrypted

    def needs_attr_enabled(self, attr, hostvars):
        sites = self.sites(hostvars)
        selected_sites = {}
        for key, site in sites.iteritems():
            if attr not in site or 'enabled' not in site[attr] or not site[attr]['enabled']:
                selected_sites[key] = {attr: {'enabled': 'C_OKtrueC_OK'}}
        return selected_sites

    def has_default_mail_password(self, hostvars):
        if 'mail_password' in hostvars and hostvars['mail_password'] == 'smtp_password':
            return True
        else:
            return False

    def has_default_mysql_root_password(self, hostvars):
        if 'mysql_root_password' in hostvars and hostvars['mysql_root_password'] in ['devpw', 'stagingpw', 'productionpw']:
            return True
        else:
            return False

    def has_default_sudoer_passwords(self, hostvars):
        if (self.env != 'development' and 'sudoer_passwords' in hostvars and
                hostvars['sudoer_passwords'] == {'admin': '$6$rounds=100000$JUkj1d3hCa6uFp6R$3rZ8jImyCpTP40e4I5APx7SbBvDCM8fB6GP/IGOrsk/GEUTUhl1i/Q2JNOpj9ashLpkgaCxqMqbFKdZdmAh26/'}):
            return True
        else:
            return False

    def has_default_db_password(self, hostvars):
        sites = self.sites(hostvars)
        selected_sites = []
        valid_sites = (site for site in sites.keys() if site in hostvars['vault_wordpress_sites'].keys())
        for key in valid_sites:
            site_vault = hostvars['vault_wordpress_sites'][key]
            if 'env' in site_vault and 'db_password' in site_vault['env'] and site_vault['env']['db_password'] == 'example_dbpassword':
                selected_sites.append(key)
        return selected_sites

    def has_default_salts(self, hostvars):
        sites = self.sites(hostvars)
        selected_sites = []
        valid_sites = (site for site in sites.keys() if site in hostvars['vault_wordpress_sites'].keys())
        for key in valid_sites:
            site_vault = hostvars['vault_wordpress_sites'][key]
            for env_key, value in site_vault['env'].iteritems():
                if env_key.endswith(('_key', '_salt')) and value == 'generateme':
                    selected_sites.append(key)
        return selected_sites

    def has_default_wp_admin_password(self, hostvars):
        sites = self.sites(hostvars)
        selected_sites = []
        if self.env == 'development':
            valid_sites = (site for site in sites.keys() if site in hostvars['vault_wordpress_sites'].keys())
            for key in valid_sites:
                site_vault = hostvars['vault_wordpress_sites'][key]
                if site_vault['admin_password'] == 'admin':
                    selected_sites.append(key)
        return selected_sites

    def cli_args_vault(self):
        if self._options.ask_vault_pass:
            return '--ask-vault-pass'
        elif self._options.vault_password_file:
            return ' '.join(['--vault-password-file', self._options.vault_password_file])
        else:
            return ''

    def v2_playbook_on_start(self, playbook):
        super(CallbackModule, self).v2_playbook_on_start(playbook)

    def v2_playbook_on_play_start(self, play):
        super(CallbackModule, self).v2_playbook_on_play_start(play)
        play.vars['playbook'] = self.playbook

        # Set vars by host
        for host in play.get_variable_manager()._inventory.list_hosts(self.hosts_param[0]):
            hostvars = self.vars[host.get_name()]

            # Initialize a few `--extra-vars` to avoid having to repeatedly use `var | default('')` in templates
            host.vars['_site'] = hostvars['site'] if 'site' in hostvars else ''
            host.vars['_env'] = hostvars['env'] if 'env' in hostvars else 'development'

            # Custom vars
            host.vars['unvaulted_sites'] = difference(self.sites(hostvars).keys(), hostvars['vault_wordpress_sites'].keys())
            host.vars['db_name_dups'] = self.db_name_dups(hostvars)
            host.vars['site_hosts_with_protocol'] = self.site_hosts_with_protocol(hostvars)
            host.vars['wp_env_no_protocol'] = self.wp_env_no_protocol(hostvars)
            host.vars['no_site_hosts_in_wp_env'] = self.no_site_hosts_in_wp_env(hostvars)
            host.vars['unencrypted_vault_files'] = self.unencrypted_vault_files(hostvars)
            host.vars['non_ssl_sites'] = self.needs_attr_enabled('ssl', hostvars)
            host.vars['non_cached_sites'] = self.needs_attr_enabled('cache', hostvars)
            host.vars['has_default_mail_password'] = self.has_default_mail_password(hostvars)
            host.vars['has_default_mysql_root_password'] = self.has_default_mysql_root_password(hostvars)
            host.vars['has_default_sudoer_passwords'] = self.has_default_sudoer_passwords(hostvars)
            host.vars['has_default_db_password'] = self.has_default_db_password(hostvars)
            host.vars['has_default_salts'] = self.has_default_salts(hostvars)
            host.vars['has_default_wp_admin_password'] = self.has_default_wp_admin_password(hostvars)
            host.vars['cli_args_vault'] = self.cli_args_vault()
            host.vars['hr'] = '-' * self.wrap_width
