# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os.path
import platform
import re
import sys

from ansible.compat.six.moves.urllib.parse import quote_plus
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.callback import CallbackBase
from ansible.plugins.filter.core import to_nice_yaml
from ansible.template import Templar
from ansible.utils.unicode import to_unicode

try:
    from trellis.plugins.callback import TrellisCallbackBase
except ImportError:
    if sys.path.append(os.path.join(os.getcwd(), 'lib')) in sys.path: raise
    sys.path.append(sys.path.append(os.path.join(os.getcwd(), 'lib')))
    from trellis.plugins.callback import TrellisCallbackBase


class CallbackModule(TrellisCallbackBase, CallbackBase):
    ''' Supplements and explains Ansible output messages '''

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = '50_messages'

    def __init__(self):

        super(CallbackModule, self).__init__()

        # Auto-populated variables
        self.inventory_file = 'hosts'
        self.hosts_web_group = []
        self.hosts_env_group = []
        self.hr = '-' * self.wrap_width
        self.loader = DataLoader()
        self.templar = {}

    def template(self, template, templar):
        template = os.path.join(os.getcwd(), 'lib/trellis/templates', template)
        with open(template) as f:
            str = f.read()
        return templar.template(str, fail_on_undefined=False)

    def search_url(self, search_string):
        base_url = 'https://github.com/roots/trellis/search?utf8=%E2%9C%93&q='
        search_params = quote_plus('{0} in:file extension:yml'.format(search_string))
        return ''.join([base_url, search_params, '&type=Code'])

    def add_missing_attribute_msg(self, result):
        if "'dict object' has no attribute" in result['msg']:
            attribute = re.match(r'.* has no attribute \'(.*)\'', result['msg']).group(1)
            task = re.match(r'(.*\: )?(.*)$', self.task).group(2)
            vars = {
                'attribute': attribute,
                'task': task,
                'search_url_attribute': self.search_url(attribute),
                'search_url_task': self.search_url(task),
                }
            msg = self.template('missing_attribute.j2', Templar(variables=vars, loader=self.loader))
            result['msg'] = '\n\n'.join([result['msg'], msg])

    def add_sudo_password_msg(self, result, host):
        user_name = self.vars[host]['ansible_user'] or self.vars[host]['ansible_ssh_user']
        vars = {
            'wrong_inventory_file': (self.playbook == 'dev.yml' and
                'module_stderr' in result and 'sudo: a password is required' in result['module_stderr']),
            'needs_ask_become_pass': (self.playbook == 'server.yml' and user_name != 'root' and
                'module_stdout' in result and 'sudo: a password is required' in result['module_stdout']),
            'user_name': user_name,
            'env': self.env,
            }
        if vars['wrong_inventory_file'] or vars['needs_ask_become_pass']:
            result['msg'] = self.template('sudo_password.j2', Templar(variables=vars, loader=self.loader))

    def add_git_clone_msg(self, result, host):
        if self.task != 'deploy : Clone project files':
            return
        vars = {
            'permission_denied': 'stderr' in result and ('Permission denied' in result['stderr'] or 'access denied' in result['stderr']),
            'repo_not_found': 'stderr' in result and 'Repository not found' in result['stderr'],
            'unknown_hostkey': 'has an unknown hostkey' in result['msg'],
            'git_not_installed': 'Failed to find required executable git' in result['msg'],
            'site': self.vars[host]['site'],
            'host': host,
            'repo': self.vars[host]['wordpress_sites'][self.vars[host]['site']]['repo'],
            'env': self.env,
            'cwd': os.getcwd(),
            'platform': platform.system(),
            }
        if vars['permission_denied'] or vars['repo_not_found'] or vars['unknown_hostkey'] or vars['git_not_installed']:
            result['msg'] = self.template('git_clone.j2', Templar(variables=vars, loader=self.loader))
            del result['stderr']

    def add_vvvv_msg(self, result, host):
        # Add example command to Ansible's suggestion to run with `-vvvv`
        if 'We recommend you re-run the command using -vvvv' in result['msg']:
            inventory = '' if not self.inventory_file else ' -i {0}'.format(self.inventory_file)
            extra_vars = ''
            if self.playbook == 'server.yml':
                extra_vars = ' -e env={0}'.format(self.env)
            elif self.playbook in ['deploy.yml', 'rollback.yml']:
                extra_vars = ' -e "env={0} site={1}"'.format(self.env, self.vars[host]['site'])
            result['msg'] = ("{0}\n```\nansible-playbook {1}{2}{3} C_BOLD-vvvvC_BOLD\n```\n"
                             ).format(result['msg'], self.playbook, inventory, extra_vars)

    def add_hostkey_msg(self, result):
        # Message explaining invalid hostkey
        if 'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!' in result['msg']:
            matches = re.search(r'(@@@@@@@@@@@.*RSA host key for (.*) has changed.*Host key verification failed.)', result['msg'], re.S)
            vars = {'hr': self.hr, 'playbook': self.playbook, 'host': matches.group(2)}
            msg = self.template('hostkey.j2', Templar(variables=vars, loader=self.loader))
            result['msg'] = '\n'.join([matches.group(1), msg])

    def add_resolve_hostname_msg(self, result, host):
        if 'Could not resolve hostname' not in result['msg']:
            return
        if host == 'your_server_ip':
            result['msg'] = ("{0}\n{1}\n\nIt appears that you need to add a valid hostname to `hosts/{2}`, replacing the text `your_server_ip`."
                             ).format(result['msg'], self.hr, self.env)
        else:
            result['msg'] = ("{0}\n{1}\n\nEnsure that the host `{2}` (probably defined in `hosts/{3}`) is a valid IP or is routable via DNS or "
                             "via entries in your `/etc/hosts` or SSH config.").format(result['msg'], self.hr, host, self.env)

    def add_ssh_timed_out_msg(self, result, host):
        if 'Operation timed out' in result['msg']:
            result['msg'] = ("{0}\n{1}\n\nEnsure that the host `{2}` (probably defined in `hosts/{3}`) is a host to which you have set up access "
                             "and ensure that the remote machine is powered on.").format(result['msg'], self.hr, host, self.env)

    def add_permission_denied_msg(self, result, host):
        if 'Permission denied' in result['msg']:
            vars = {
                'passphrase_given': 'passphrase given, try' in result['msg'],
                'key_exists': 'we sent a publickey packet' in result['msg'],
                'user_var': 'web_user' if self.playbook == 'deploy.yml' else 'admin_user',
                'user_name': self.vars[host]['ansible_user'] or self.vars[host]['ansible_ssh_user'],
                'playbook': self.playbook,
                'cwd': os.getcwd(),
                'hr': self.hr,
                'platform': platform.system(),
                }
            msg = self.template('permission_denied.j2', Templar(variables=vars, loader=self.loader))
            result['msg'] = '\n'.join([result['msg'], msg])

    def add_connection_refused_msg(self, result, host):
        if 'Connection refused' not in result['msg']:
            return
        host_spec = re.search(r'connect to host (.*?): Connection refused', result['msg'])
        if host_spec is None or host_spec.group(1) == host:
            host_info = ''
        else:
            host_info = ''.join([' (`', host_spec.group(1), '`)'])
        result['msg'] = "{0}\n{1}\n\nEnsure that the host `{2}`{3} is powered on and accessible".format(result['msg'], self.hr, host, host_info)

    def add_env_msg(self, playbook):
        if self.playbook == 'dev.yml':
            return
        env_missing = False
        plays = playbook.get_plays()
        for play in plays:
            vars = play.get_variable_manager().get_vars(loader=playbook._loader, play=play)
            if 'env' not in vars:
                env_missing = True
        if not env_missing:
             return
        extra_vars = '"env=<environment> site=<sitename>"'
        if self.playbook == 'server.yml':
            extra_vars = 'env=<environment>'
        msg = ("Environment group is undefined. Try defining `env` using `-e` option:"
               "\n```\nansible-playbook {0} C_BOLD-e {1}C_BOLD\n```\n").format(self.playbook, extra_vars)
        playbook._result = dict(play_error=True, msg=msg)

    def add_msgs(self, result, host, index=None):
        # Handle looping tasks (e.g., tasks using `with_items` or `with_dict` etc.)
        if 'results' in result:
            results = (res for res in result['results'] if 'skipped' not in res)
            for i, res in enumerate(results):
                self.add_msgs(res, host, i)
            return
        # Supplement and/or explain various error messages
        self.add_missing_attribute_msg(result)
        self.add_git_clone_msg(result, host)
        self.add_sudo_password_msg(result, host)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.add_msgs(result._result, result._host.get_name())

    def v2_runner_on_unreachable(self, result):
        res = result._result
        host = result._host.get_name()
        self.add_vvvv_msg(res, host)
        self.add_hostkey_msg(res)
        self.add_resolve_hostname_msg(res, host)
        self.add_ssh_timed_out_msg(res, host)
        self.add_permission_denied_msg(res, host)
        self.add_connection_refused_msg(res, host)

    def v2_playbook_on_start(self, playbook):
        super(CallbackModule, self).v2_playbook_on_start(playbook)
        self.add_env_msg(playbook)

    def v2_playbook_on_no_hosts_matched(self):
        expected_hosts_param = 'web:&{0}'.format(self.env)
        if self.play_obj.get_name() != 'Determine Remote User' and self.hosts_param[0] == expected_hosts_param:
            vars = {
                'hosts_param': self.hosts_param[0],
                'env': self.env,
                'inventory': self.inventory_file,
                'hosts_web_group': self.hosts_web_group,
                'hosts_env_group': self.hosts_env_group,
                }
            msg = self.template('no_hosts_matched.j2', Templar(variables=vars, loader=self.loader))
            self.play_obj._result = dict(play_error=True, msg=msg)

    def v2_playbook_on_task_start(self, task, is_conditional):
        super(CallbackModule, self).v2_playbook_on_task_start(task, is_conditional)

    def v2_playbook_on_handler_task_start(self, task):
        super(CallbackModule, self).v2_playbook_on_handler_task_start(task)

    def v2_playbook_on_play_start(self, play):
        super(CallbackModule, self).v2_playbook_on_play_start(play)
        self.disabled = not self.custom_output
        self.hosts_web_group = [host.name for host in play.get_variable_manager()._inventory.list_hosts('web')]
        self.hosts_env_group = [host.name for host in play.get_variable_manager()._inventory.list_hosts(self.env)]

        # Set vars that are the same for all hosts
        magic_vars = play.get_variable_manager()._get_magic_variables(loader=self.loader, play=play, host=None,
            task=None, include_hostvars=False, include_delegate_to=False)
        self.inventory_file = magic_vars['inventory_file'] or magic_vars['inventory_dir'].replace(os.getcwd(), '').lstrip('/')

        # Set templars by host
        for host in play.get_variable_manager()._inventory.list_hosts(self.hosts_param[0]):
            hostname = host.get_name()
            self.templar[hostname] = Templar(variables=self.vars[hostname], loader=self.loader)
