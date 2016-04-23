# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

def vvvv(obj, result, host):
    # Add example command to Ansible's suggestion to run with `-vvvv`
    if 'We recommend you re-run the command using -vvvv' in result['msg']:
        inventory = '' if not obj.inventory_file else ' -i {0}'.format(obj.inventory_file)
        extra_vars = ''
        if obj.playbook == 'server.yml':
            extra_vars = ' -e env={0}'.format(obj.env)
        elif obj.playbook in ['deploy.yml', 'rollback.yml']:
            extra_vars = ' -e "env={0} site={1}"'.format(obj.env, obj.vars[host]['site'])
        result['msg'] = ("{0}\nansible-playbook {1}{2}{3} -vvvv"
                         ).format(result['msg'], obj.playbook, inventory, extra_vars)

def hostkey(obj, result):
    # Message explaining invalid hostkey
    if 'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!' in result['msg']:
        matches = re.search(r'(@@@@@@@@@@@.*RSA host key for (.*) has changed.*Host key verification failed.)', result['msg'], re.S)
        vars = {'hr': obj.hr, 'playbook': obj.playbook, 'host': matches.group(2)}
        msg = obj.template('hostkey.j2', Templar(variables=vars, loader=obj.loader))
        result['msg'] = '\n'.join([matches.group(1), msg])

def resolve_hostname(obj, result, host):
    if 'Could not resolve hostname' not in result['msg']:
        return
    if host == 'your_server_ip':
        result['msg'] = ("{0}\n{1}\n\nIt appears that you need to add a valid hostname to `hosts/{2}`, replacing the text `your_server_ip`."
                         ).format(result['msg'], obj.hr, obj.env)
    else:
        result['msg'] = ("{0}\n{1}\n\nEnsure that the host `{2}` (probably defined in `hosts/{3}`) is a valid IP or is routable via DNS or "
                         "via entries in your `/etc/hosts` or SSH config.").format(result['msg'], obj.hr, host, obj.env)

def ssh_timed_out(obj, result, host):
    if 'Operation timed out' in result['msg']:
        result['msg'] = ("{0}\n{1}\n\nEnsure that the host `{2}` (probably defined in `hosts/{3}`) is a host to which you have set up access "
                         "and ensure that the remote machine is powered on.").format(result['msg'], obj.hr, host, obj.env)

def permission_denied(obj, result, host):
    if 'Permission denied' in result['msg']:
        vars = {
            'passphrase_given': 'passphrase given, try' in result['msg'],
            'key_exists': 'we sent a publickey packet' in result['msg'],
            'user_var': 'web_user' if obj.playbook == 'deploy.yml' else 'admin_user',
            'user_name': obj.vars[host]['ansible_user'] or obj.vars[host]['ansible_ssh_user'],
            'playbook': obj.playbook,
            'cwd': os.getcwd(),
            'hr': obj.hr,
            'platform': platform.system(),
            }
        msg = obj.template('permission_denied.j2', Templar(variables=vars, loader=obj.loader))
        result['msg'] = '\n'.join([result['msg'], msg])

def connection_refused(obj, result, host):
    if 'Connection refused' not in result['msg']:
        return
    host_spec = re.search(r'connect to host (.*?): Connection refused', result['msg'])
    if host_spec is None or host_spec.group(1) == host:
        host_info = ''
    else:
        host_info = ''.join([' (`', host_spec.group(1), '`)'])
    result['msg'] = "{0}\n{1}\n\nEnsure that the host `{2}`{3} is powered on and accessible".format(result['msg'], obj.hr, host, host_info)

def unreachable(obj, result):
    res = result._result
    host = result._host.get_name()
    # vvvv(res, host)
    # hostkey(res)
    # resolve_hostname(res, host)
    # ssh_timed_out(res, host)
    # permission_denied(res, host)
    # connection_refused(res, host)
