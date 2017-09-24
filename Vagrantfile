# -*- mode: ruby -*-
# vi: set ft=ruby :

ANSIBLE_PATH = __dir__ # absolute path to Ansible directory on host machine
ANSIBLE_PATH_ON_VM = '/home/vagrant/trellis' # absolute path to Ansible directory on virtual machine

require File.join(ANSIBLE_PATH, 'lib', 'trellis', 'vagrant')
require File.join(ANSIBLE_PATH, 'lib', 'trellis', 'config')
require 'yaml'

vconfig_global = YAML.load_file("#{ANSIBLE_PATH}/vagrant.default.yml")

if File.exist?("#{ANSIBLE_PATH}/vagrant.local.yml")
  local_config = YAML.load_file("#{ANSIBLE_PATH}/vagrant.local.yml")
  vconfig_global.merge!(local_config) if local_config
end

ensure_plugins(vconfig_global.fetch('vagrant_plugins')) if vconfig_global.fetch('vagrant_install_plugins')

trellis_config = Trellis::Config.new(root_path: ANSIBLE_PATH, vconfig: vconfig_global)
bin_path = File.join(ANSIBLE_PATH_ON_VM, 'bin')
provisioner = local_provisioning? ? :ansible_local : :ansible
provisioning_path = local_provisioning? ? ANSIBLE_PATH_ON_VM : ANSIBLE_PATH

machines = trellis_config.machines
machines_selected = trellis_config.machines_selected
validate_ips(machines, machines_selected)

Vagrant.require_version '>= 1.8.5'

Vagrant.configure('2') do |config|

  # Fix for: "stdin: is not a tty"
  # https://github.com/mitchellh/vagrant/issues/1673#issuecomment-28288042
  config.ssh.shell = %{bash -c 'BASH_ENV=/etc/profile exec bash'}

  config.ssh.forward_agent = true

  # https://github.com/devopsgroup-io/vagrant-hostmanager/issues/179
  if Vagrant.has_plugin?('vagrant-hostmanager')
    config.hostmanager.enabled = true
    config.hostmanager.manage_host = true
  end

  machines.each_pair do |vm_name, _machine|
    vconfig = _machine['vconfig']
    vagrant_autostart = machines.size == 1 ? true : _machine['vagrant_autostart']
    vm_ip = _machine.fetch('ip', vconfig.fetch('vagrant_ip'))

    config.vm.define vm_name, primary: _machine['vagrant_primary'], autostart: vagrant_autostart do |machine|
      machine.vm.box = vconfig.fetch('vagrant_box')
      machine.vm.box_version = vconfig.fetch('vagrant_box_version')
      machine.vm.hostname = _machine['site_hosts'].first
      machine.vm.post_up_message = post_up_message


      # NETWORKING
      # ------------------------------------------
      # Required for NFS to work
      if vm_ip == 'dhcp'
        machine.vm.network :private_network, type: 'dhcp', hostsupdater: 'skip'

        cached_addresses = {}
        machine.hostmanager.ip_resolver = proc do |vm, _resolving_vm|
          if cached_addresses[vm.name].nil?
            if vm.communicate.ready?
              vm.communicate.execute("hostname -I | cut -d ' ' -f 2") do |type, contents|
                cached_addresses[vm.name] = contents.split("\n").first[/(\d+\.\d+\.\d+\.\d+)/, 1]
              end
            end
          end
          cached_addresses[vm.name]
        end
      else
        machine.vm.network :private_network, ip: vm_ip, hostsupdater: 'skip'
      end

      if Vagrant.has_plugin?('vagrant-hostmanager') && !_machine['multisite_subdomains']
        machine.hostmanager.aliases = _machine['site_hosts']
      elsif Vagrant.has_plugin?('landrush') && _machine['multisite_subdomains']
        machine.landrush.enabled = true
        machine.landrush.tld = _machine['site_hosts'].first
        _machine['site_hosts'].each { |host| machine.landrush.host host, vm_ip }
      else
        fail_with_message "vagrant-hostmanager missing, please install the plugin with this command:\nvagrant plugin install vagrant-hostmanager\n\nOr install landrush for multisite subdomains:\nvagrant plugin install landrush"
      end


      # SYNCED FOLDERS
      # ------------------------------------------
      if Vagrant::Util::Platform.windows? and !Vagrant.has_plugin? 'vagrant-winnfsd'
        _machine['site_paths'].each_pair do |name, paths|
          machine.vm.synced_folder local_site_path(paths), remote_site_path(name, paths), owner: 'vagrant', group: 'www-data', mount_options: ['dmode=776', 'fmode=775']
        end

        machine.vm.synced_folder ANSIBLE_PATH, ANSIBLE_PATH_ON_VM, mount_options: ['dmode=755', 'fmode=644']
        machine.vm.synced_folder File.join(ANSIBLE_PATH, 'bin'), bin_path, mount_options: ['dmode=755', 'fmode=755']
      else
        if !Vagrant.has_plugin? 'vagrant-bindfs'
          fail_with_message "vagrant-bindfs missing, please install the plugin with this command:\nvagrant plugin install vagrant-bindfs"
        else
          _machine['site_paths'].each_pair do |name, paths|
            machine.vm.synced_folder local_site_path(paths), nfs_path(name), type: 'nfs'
            machine.bindfs.bind_folder nfs_path(name), remote_site_path(name, paths), u: 'vagrant', g: 'www-data', o: 'nonempty'
          end

          machine.vm.synced_folder ANSIBLE_PATH, '/ansible-nfs', type: 'nfs'
          machine.bindfs.bind_folder '/ansible-nfs', ANSIBLE_PATH_ON_VM, o: 'nonempty', p: '0644,a+D'
          machine.bindfs.bind_folder File.join(ANSIBLE_PATH_ON_VM, 'hosts'), File.join(ANSIBLE_PATH_ON_VM, 'hosts'), perms: '0755'
          machine.bindfs.bind_folder bin_path, bin_path, perms: '0755'
        end
      end

      vconfig.fetch('vagrant_synced_folders', []).each do |folder|
        options = {
          type: folder.fetch('type', 'nfs'),
          create: folder.fetch('create', false),
          mount_options: folder.fetch('mount_options', [])
        }

        destination_folder = folder.fetch('bindfs', true) ? nfs_path(folder['destination']) : folder['destination']

        machine.vm.synced_folder folder['local_path'], destination_folder, options

        if folder.fetch('bindfs', true)
          machine.bindfs.bind_folder destination_folder, folder['destination'], folder.fetch('bindfs_options', {})
        end
      end


      # PROVISIONING
      # ------------------------------------------
      if provisioner == :ansible_local or vm_name == machines_selected.last
        machine.vm.provision provisioner do |ansible|
          if local_provisioning?
            ansible.install_mode = 'pip'
            ansible.provisioning_path = provisioning_path
            ansible.version = vconfig.fetch('vagrant_ansible_version')
          end

          ansible.inventory_path = File.join(provisioning_path, 'hosts/hosts.py')
          ansible.limit =  machines_selected.join(',') if provisioner == :ansible
          ansible.playbook = File.join(provisioning_path, 'dev.yml')
          ansible.galaxy_role_file = File.join(provisioning_path, 'requirements.yml') unless vconfig.fetch('vagrant_skip_galaxy') || ENV['SKIP_GALAXY']
          ansible.galaxy_roles_path = File.join(provisioning_path, 'vendor/roles')

          ansible.tags = ENV['ANSIBLE_TAGS']
          ansible.extra_vars = {
            'vagrant_provisioner' => true,
            'vagrant_version' => Vagrant::VERSION,
            'vagrant_machines' => machines_selected,
            'vagrant_machine' => vm_name
          }
          config.ssh.forward_agent = false
          # ansible.verbose = 'vvv'

          if vars = ENV['ANSIBLE_VARS']
            extra_vars = Hash[vars.split(',').map { |pair| pair.split('=') }]
            ansible.extra_vars.merge!(extra_vars)
          end
        end
      end


      # PROVIDERS
      # ------------------------------------------
      # Virtualbox settings
      machine.vm.provider 'virtualbox' do |vb|
        vb.name = vm_name
        vb.customize ['modifyvm', :id, '--cpus', vconfig.fetch('vagrant_cpus')]
        vb.customize ['modifyvm', :id, '--memory', vconfig.fetch('vagrant_memory')]
        vb.customize ['modifyvm', :id, '--ioapic', vconfig.fetch('vagrant_ioapic', 'on')]

        # Fix for slow external network connections
        vb.customize ['modifyvm', :id, '--natdnshostresolver1', vconfig.fetch('vagrant_natdnshostresolver', 'on')]
        vb.customize ['modifyvm', :id, '--natdnsproxy1', vconfig.fetch('vagrant_natdnsproxy', 'on')]
      end

      # VMware Workstation/Fusion settings
      ['vmware_fusion', 'vmware_workstation'].each do |provider|
        machine.vm.provider provider do |vmw, override|
          vmw.name = vm_name
          vmw.vmx['numvcpus'] = vconfig.fetch('vagrant_cpus')
          vmw.vmx['memsize'] = vconfig.fetch('vagrant_memory')
        end
      end

      # Parallels settings
      machine.vm.provider 'parallels' do |prl, override|
        prl.name = vm_name
        prl.cpus = vconfig.fetch('vagrant_cpus')
        prl.memory = vconfig.fetch('vagrant_memory')
        prl.update_guest_tools = true
      end
    end
  end
end
