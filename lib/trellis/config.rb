# frozen_string_literal: true

require 'vagrant'
require 'yaml'

module Trellis
  class Config
    def initialize(root_path:, vconfig:)
      @root_path = root_path
      @vconfig = vconfig
    end

    def machine_from_hostvars(group, data, projects_with_dev, groups)
      machine = {
        'ip' => '',
        'site_paths' => {},
        'site_hosts' => [],
        'multisite_subdomains' => []
      }

      # add data from hosts/hosts.yml, primarily IP
      host = data['web']['development']
      if host.is_a? String
        machine['ip'] = host
      elsif host.first.is_a? String
        machine['ip'] = host.first
      elsif host.first.is_a? Hash
        # get all vars; they could include `vagrant_primary`, `vagrant_autostart`, `base_project`
        machine.merge!(host.first)
        machine['ip'] = machine.delete('ansible_host') if machine.has_key?('ansible_host')
      end

      machine
    end

    def get_children(group, groups, children=[])
      groups.fetch(group, {}).fetch('children', []).each do |child|
        children.push(child)
        get_children(child, groups, children)
      end

      children
    end

    def get_parents_from_groups(child, groups, parents=[])
      groups.each do |name, data|
        if data.has_key?('children') and data['children'].include?(child)
          parents.push(name)
          get_parents_from_groups(name, groups, parents)
        end
      end

      parents
    end

    def get_parents(group, hosts_data)
      parents = []
      parents.concat(hosts_data['projects'][group].fetch('parents', [])) if hosts_data['projects'].has_key?(group)
      parents.concat([group]).each do |g|
        parents.concat(get_parents_from_groups(g, hosts_data.fetch('groups', {})))
      end
      parents.concat(['development', 'all', 'all-projects']).uniq
    end

    def get_target_projects(group, projects_with_dev, groups)
      # retrieve child projects, if any
      if group == 'all-projects'
        children = projects_with_dev.keys
      else
        children = get_children(group, groups)
        children.select { |child| projects_with_dev.keys.include?(child) }
      end
      children.uniq!

      children.any? ? children.sort : [group]
    end

    def combine_for_groups(groups, site_vars_to_combine)
      site_vars = {}

      site_vars_to_combine.each do |item|
        # minimal version of https://github.com/ansible/ansible/blob/f921369/lib/ansible/inventory/manager.py#L311
        item.each do |pattern,vars|
          patterns = pattern.split(/,|:/)

          # order patterns https://github.com/ansible/ansible/blob/f921369/lib/ansible/inventory/manager.py#L49
          pattern_regular = []
          pattern_intersection = []
          pattern_exclude = []

          patterns.each do |p|
            if p.start_with?('!')
              pattern_exclude.push(p)
            elsif p.start_with?('&')
              pattern_intersection.push(p)
            else
              pattern_regular.push(p)
            end
          end

          patterns = pattern_regular + pattern_intersection + pattern_exclude

          # evaluate patterns https://github.com/ansible/ansible/blob/f921369/lib/ansible/inventory/manager.py#L364
          matches = []

          patterns.each do |p|
            _p = p.start_with?('!', '&') ? p[1..-1] : p
            if _p.start_with?('~')
              _p = "/#{_p[1..-1]}/i".to_regexp
            elsif _p.include?('*')
              _p = "/^#{_p.gsub('*', '.*')}$/i".to_regexp
            end

            candidates = groups.grep(_p)

            if p.start_with?('!')
              matches -= candidates
            elsif p.start_with?('&')
              matches &= candidates
            else
              matches.concat(candidates).uniq!
            end
          end

          # Note: not implementing pattern-matching for subscripts http://docs.ansible.com/ansible/latest/intro_patterns.html
          # Note: whereas Ansible's pattern_parser returns a list of hosts matching, ours returns groups (`matches`)
          site_vars.deep_merge!(vars) if matches.any?
        end
      end

      site_vars
    end

    def get_site_paths(site, vars)
      paths = {
        site => {
          'local' => vars.fetch('local_path', '').gsub(/{{ site.*}}/, site),
          'current' => vars.fetch('current_path', 'current')
        }
      }
      paths
    end

    def get_site_hosts(site, vars, project_path)
      # validate site_hosts format
      vars['site_hosts'].each do |host|
        if !host.is_a?(Hash) || !host.has_key?('canonical')
          fail_with_message File.read(File.join(ANSIBLE_PATH, 'roles/dynamic-hosts/templates/site_hosts.j2')).sub!('{{ env }}', 'development').gsub!(/com$/, 'dev').sub!('{{ project_path }}', project_path)
        end
      end

      _site_hosts = vars['site_hosts'].flat_map { |host| [host['canonical']] + host.fetch('redirects', []) }
      _site_hosts.map! { |h| h.gsub(/{{ site.*}}/, site) }
    end

    def machines
      @machines ||= begin
        hosts_data = YAML.load_file(File.join(ANSIBLE_PATH, 'hosts/hosts.yml'))
        projects_with_dev = hosts_data['projects'].select { |group,data| data.fetch('web', {}).include?('development') }
        _groups = hosts_data.fetch('groups', {}).select { |group,data| data.fetch('web', {}).include?('development') }.merge(projects_with_dev)

        # sort groups (machines) according to machine order specified on CLI, if any
        # vagrant boots VMs in order specified on CLI
        # `machines` and `machines_selected` must have the same order for correct Ansible parallel provisioning
        # provisioning is conditional on `vm_name == machines_selected.last`
        groups = {}
        machines_selected(candidates: _groups).each do |name|
          groups[name] = _groups.delete(name)
        end
        groups.merge!(_groups)

        # prepare vars that will be used throughout loop below
        site_vars_default = YAML.load_file(File.join(ANSIBLE_PATH, 'group_vars/all/site_vars_default.yml'))['site_vars_default']
        site_vars_global = YAML.load_file(File.join(ANSIBLE_PATH, 'group_vars/all/site_vars.yml'))['site_vars_global']
        project_path_var = YAML.load_file(File.join(ANSIBLE_PATH, 'group_vars/all/main.yml'))['project_path']
        _site_vars = {}
        site_paths = {}
        site_hosts = {}
        multisite_subdomains = {}
        groups_to_match = {}
        machines = {}

        # assemble info per machine
        groups.each_pair do |group, data|
          machine = machine_from_hostvars(group, data, projects_with_dev, hosts_data.fetch('groups', {}))
          target_projects = get_target_projects(group, projects_with_dev, hosts_data.fetch('groups', {}))

          # merge base_project's `vagrant.local.yml` file, if any
          base_project_path = project_path_var.gsub(/{{ project.*}}/, machine['base_project'] || target_projects.first)
          machine['vconfig'] = @vconfig
          if File.exist?("#{ANSIBLE_PATH}/#{base_project_path}/vagrant.local.yml")
            machine['vconfig'].merge!(YAML.load_file("#{ANSIBLE_PATH}/#{base_project_path}/vagrant.local.yml"))
          end

          machine['vagrant_autostart'] ||= machine['vconfig'].fetch('vagrant_autostart', false)

          # get vars per remaining project
          target_projects.reject { |p| _site_vars.include? p }.each do |project|
            project_path = project_path_var.gsub(/{{ project.*}}/, project)
            _site_vars[project] ||= YAML.load_file(File.join(ANSIBLE_PATH, project_path, 'vars/all/site_vars.yml'))
            groups_to_match[project] ||= get_parents(project, hosts_data) + [project]

            # process site_vars_default, site_vars_global and site_vars_for_project
            site_vars = combine_for_groups(groups_to_match[project], site_vars_default)
            site_vars.deep_merge!(combine_for_groups(groups_to_match[project], site_vars_global))
            site_vars.deep_merge!(combine_for_groups(groups_to_match[project], _site_vars[project].fetch('site_vars_for_project', {})))

            # process site_vars
            site_paths[project] = {}
            site_hosts[project] = []
            multisite_subdomains[project] = []

            _site_vars[project]['site_vars'].each_pair do |site,_vars|
              vars = site_vars
              vars.deep_merge!(combine_for_groups(groups_to_match[project], _vars))
              site_paths[project].merge!(get_site_paths(site, vars))
              site_hosts[project].concat(get_site_hosts(site, vars, project_path))
              multisite_subdomains[project].push(vars['multisite'].fetch('enabled', false) && vars['multisite'].fetch('subdomains', false))
            end
          end

          # supply machine with info for target projects
          target_projects.each do |p|
            machine['site_paths'].merge!(site_paths[p])
            machine['site_hosts'].concat(site_hosts[p]).uniq!
            machine['multisite_subdomains'] = multisite_subdomains[p].include? true
          end

          machines[group] = machine
        end

        machines
      end
    end

    # limit machines to those specified in vagrant command, if any, or to machines designated to autostart
    # Note: "If Vagrant sees a machine name within forward slashes, it assumes you are using a regular expression."
    #       https://www.vagrantup.com/docs/multi-machine/#controlling-multiple-machines
    def machines_selected(candidates: @machines)
      @machines_selected ||= begin
        selected = candidates.keys

        if ['up', 'provision', 'hostmanager'].include?(ARGV[0]) or ARGV.include?('--provision')
          machine_names = ARGV[1..-1].grep(/^(?!.*--)/).map { |pattern| candidates.keys.grep(pattern.match(/\/.+\//) ? pattern.to_regexp : pattern) }
          if !machine_names.flatten.empty?
            selected = machine_names.flatten & candidates.keys
          elsif ARGV[0] == 'up' and candidates.keys.size > 1
            selected = candidates.select { |name,data| data['vagrant_autostart'] }.keys
          end
        end

        selected
      end
    end
  end
end
