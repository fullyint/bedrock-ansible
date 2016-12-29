# ssh-hardening (Ansible Role)

## Description

This role provides secure ssh-client and ssh-server configurations.

## Requirements

* Ansible

## Role Variables
| Name           | Default Value | Description                        |
| -------------- | ------------- | -----------------------------------|
|`ssh_client_hardening` | `true` | `true` to apply this role's settings and template to `/etc/ssh/ssh_config`.|
|`ssh_server_hardening` | `true` | `true` to apply this role's settings and template to `/etc/ssh/sshd_config`.|
|`ssh_client_cbc_required` | `false` | `false` to avoid CBC mode ciphers.|
|`ssh_server_cbc_required` | `false` | `false` to avoid CBC mode ciphers.|
|`ssh_ciphers_default` | `['chacha20-poly1305@openssh.com',`<br/>` 'aes256-gcm@openssh.com',`<br/>` 'aes128-gcm@openssh.com',`<br/>` 'aes256-ctr',`<br/>` 'aes192-ctr',`<br/>` 'aes128-ctr']` | Ciphers to allow.|
|`ssh_ciphers_weak` | `['aes256-cbc',`<br/>` 'aes192-cbc',`<br/>` 'aes128-cbc']` | Additional ciphers to allow when `*_cbc_required: true`.|
|`ssh_client_weak_hmac` | `false` | `false` to avoid weaker message authentication codes (MACs).|
|`ssh_server_weak_hmac` | `false` | `false` to avoid weaker MACs.|
|`ssh_macs_default` | `['hmac-sha2-512-etm@openssh.com',`<br/>` 'hmac-sha2-256-etm@openssh.com',`<br/>` 'hmac-ripemd160-etm@openssh.com',`<br/>` 'umac-128-etm@openssh.com',`<br/>` 'hmac-sha2-512',`<br/>` 'hmac-sha2-256',`<br/>` 'hmac-ripemd160']` | MACs to make available.|
|`ssh_macs_weak` | `['umac-128@openssh.com',`<br/>` 'hmac-sha1']` | Additional MACs to make available when `*_weak_hmac: true`.|
|`ssh_client_weak_kex` | `false` | `false` to avoid weaker Key Exchange (KEX) algorithms.|
|`ssh_server_weak_kex` | `false` | `false` to avoid weaker KEX algorithms.|
|`ssh_kex_default` | `['curve25519-sha256@libssh.org',`<br/>` 'diffie-hellman-group-exchange-sha256']` | KEX algorithms to make available.|
|`ssh_kex_weak` | `['diffie-hellman-group14-sha1',`<br/>` 'diffie-hellman-group-exchange-sha1',`<br/>` 'diffie-hellman-group1-sha1']` | Additional KEX algorithms to make available when `*_weak_kex: true`.|
|`ssh_client_password_login` | `false` | `false` for client to forbid password login.|
|`ssh_server_password_login` | `false` | `false` for server to forbid password login.|
|`network_ipv6_enable` | `false` | Set to `true` if IPv6 is needed.|
|`ssh_client_port` | `22` | Port to which the client should connect.|
|`ssh_server_ports` | `['22']` | Ports on which the server should listen.|
|`ssh_listen_to` | `['0.0.0.0']` | IPs to which the server should listen.|
|`ssh_strict_hostkey_checking` | `ask` | Policy on adding keys to `known_hosts`.|
|`ssh_identity_files`| `['~/.ssh/id_ed25519',`<br/>` '~/.ssh/id_rsa']` | SSH key files the client should try.|
|`ssh_host_key_files` | `['/etc/ssh/ssh_host_ed25519_key',`<br/>` '/etc/ssh/ssh_host_rsa_key']` | Host keys the server should use.|
|`ssh_host_key_algorithms` | `['ssh-ed25519-cert-v01@openssh.com',`<br/>` 'ssh-rsa-cert-v01@openssh.com',`<br/>` 'ssh-ed25519',`<br/>` 'ssh-rsa']` | Host key algorithms that the ssh-client wants to use, in order of preference.|
|`ssh_max_auth_retries` | `6` | The maximum number of authentication attempts permitted per connection. Once the number of failures reaches half this value, additional failures are logged.|
|`ssh_client_alive_interval` | `600` | The number of seconds of inactivity before the server should send keepalive message.|
|`ssh_client_alive_count` | `3` | The number of keepalive messages the server should send (without response) before disconnecting.|
|`ssh_remote_hosts` | `[]` | Hosts and their custom options for the ssh-client. Examples in `defaults/main.yml`.|
|`ssh_allow_root_with_key` | `true` | `true` to allow `root` user to login via SSH key. Set to `false` to disable `root` login.|
|`ssh_allow_tcp_forwarding` | `false` | `false` to disable TCP forwarding.|
|`ssh_allow_agent_forwarding` | `true` | `true` to allow agent forwarding.|
|`ssh_use_pam` | `true` | PAM authentication enabled to avoid Debian [bug #751636](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=751636) with openssh-server.|
|`ssh_deny_users` | `[]` | User name patterns forbidden login.|
|`ssh_allow_users` | `[]` | The only user name patterns granted login.|
|`ssh_deny_groups` | `[]` | Group name patterns forbidden login.|
|`ssh_allow_groups` | `[]` | The only group name patterns granted login.|
|`ssh_print_motd` | `false` | `false` to disable printing the MOTD.|
|`ssh_print_last_log` | `false` | `false` to disable display of previous login info.|
|`ssh_banner` | `false` | `false` to withhold `/etc/ssh/banner.txt` during pre-authentication.|
|`ssh_print_debian_banner` | `false` | `false` to disable distribution version leakage during initial protocol handshake.|
|`ssh_send_env` | `[]` | List of environment variables the ssh-client should send to the remote server.|
|`ssh_accept_env` | `[]` | List of environment variables sent by the client that will be copied into the server's session environ. Avoid accepting any.|
|`sftp_enabled` | `true` | `true` to enable sftp configuration.|
|`sftp_chroot_dir` | `/home/%u` | The default sftp `chroot` directory.|
|`ssh_client_roaming` | `false` | `false` to disable client roaming.|

## FAQ / Pitfalls

### I can't log into my account. I have registered the client key, but it still doesn't let me in.

If you have exhausted all typical issues (firewall, network, key missing, wrong key, account disabled etc.), it may be that your account is locked. The quickest way to find out is to look at the password hash for your user:

    sudo grep myuser /etc/shadow

If the hash includes an `!`, your account is locked:

    myuser:!:16280:7:60:7:::

The proper way to solve this is to unlock the account (`passwd -u myuser`). If the user doesn't have a password, you can unlock it via:

    usermod -p "*" myuser

Alternatively, PAM will allow locked users to get in with keys. PAM is enabled via role variable `ssh_use_pam: true`.


### Why doesn't my application connect via SSH anymore?

Always look into log files first, ideally evaluating the intial negotation of the connection between client and server.

Some python and ruby applications use an outdated crypto set, possibly requiring you to use `true` for this role's variables for `*_cbc_required`, `*_weak_hmac`, or `*_weak_kex`.

### After using this role, Ansible's template/copy/file module stops working!

If you set `sftp_enabled: false`, you must uncomment `scp_if_ssh = True` in your `ansible.cfg`. This way Ansible uses SCP to copy files instead of the default SFTP.

### I cannot restart sshd-service due to lack of privileges.

If you get the following error when running handler "restart sshd"
```
Unable to restart service ssh: Failed to restart ssh.service: Access denied
```
or
```
failure 1 running systemctl show for 'ssh': Failed to connect to bus: No such file or directory
```
either run the playbook as `root` (without `become: yes` at the playbook level), or add `become: yes` to the handler.

This is a bug with Ansible: see [here](https://github.com/dev-sec/ansible-ssh-hardening/pull/81) and [here](https://github.com/ansible/ansible/issues/17490) for more information.

## Attribution

This role has been modified from the original to work with the defaults that have been established in Trellis.

Many thanks to [dev-sec](https://github.com/dev-sec/) for creating the [original version](https://github.com/dev-sec/ansible-ssh-hardening) of this role.
