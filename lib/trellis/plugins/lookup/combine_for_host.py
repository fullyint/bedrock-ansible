# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
'''
Lookup plugin to combine a list of dictionaries by prioritized host pattern
========================================================================================

The `combine_for_host` lookup plugin offers a means of achieving hash_behavior=merge for a
specified variable, with explicit priority by host pattern. It can achieve a variable precedence
that otherwise could require complicated parent/child relationships between Ansible groups.

The `combine_for_host` lookup plugin expects each variable submitted to be a list of dictionaries,
where each dictionary key is a host pattern and the value is a dictionary of configs.
Dictionaries are submitted to the Ansible `combine` filter (recursive=True by default).
Priority increases as the list goes on. Items later in the list have priority over earlier items.
For info about host patterns, see http://docs.ansible.com/ansible/intro_patterns.html

---
# example variable listing dictionaries to be merged:
something_to_combine:
  - all:
      some_config: foo
      other_config: bar
  - web:&production:
      some_config: production_foo

another_to_combine:
  - db:&production:
      some_config: db_production_foo

# basic merge -- basic plugin usage
merged_var: "{{ lookup('combine_for_host', something_to_combine) }}"
  # Yields the following for a host that is in both the `web` and `production` groups:
  #  merged_var:
  #    some_config: production_foo
  #    other_config: bar

# possible to merge multiple vars
merged_var_multi: "{{ lookup('combine_for_host', something_to_combine, another_to_combine) }}"

# evaluates current `inventory_hostname` against host pattern (default), but accepts `host` override via kwarg
merged_var_based_on_other_host: "{{ lookup('combine_for_host', something_to_combine, host='some_other_host') }}"

# utilizes Ansible's `combine` filter with recursive=True as default, but accepts `recursive` kwarg
# note: when `recursive=False`, later configs that are dicts completely replace earlier configs
merged_var_non_recursive: "{{ lookup('combine_for_host', something_to_combine, recursive=False) }}"

'''
from ansible.errors import AnsibleError
from ansible.module_utils.six import iteritems
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.filter.core import combine
from ansible.plugins.lookup import LookupBase
from ansible.template import Templar


class LookupModule(LookupBase):
    ''' Combine hashes whose key/pattern matches current host '''

    def check_type(self, item):
        if not isinstance(item, dict):
            raise AnsibleError('\n\n`combine_for_host` expects each variable submitted to be a list of\n'
                    'dictionaries, where each dictionary key is a host pattern and\n'
                    'the value is a dictionary of configs. For info about host patterns,\n'
                    'see http://docs.ansible.com/ansible/intro_patterns.html\n\n'
                    'Example variable format:\n\n'
                    'something_to_combine:\n'
                    '  - all:\n'
                    '      some_config: foo\n'
                    '      other_config: bar\n'
                    '  - web:&production:\n'
                    '      some_config: production_foo\n\n'
                    'Here is the problematic item that caused the error:\n\n{}\n'.format(repr(item)))

    def run(self, terms, variables=None, wantlist=True, recursive=True, **kwargs):
        lookup = Templar(variables=variables, loader=DataLoader())._lookup
        host = kwargs.pop('host', variables['inventory_hostname'])
        dicts_to_combine = [{}]

        for term in LookupBase._flatten(terms):
            if term is None:
                continue

            self.check_type(term)

            for pattern,data in term.iteritems():
                if data is None:
                    continue

                self.check_type(data)
                if host in lookup('inventory_hostnames', pattern, wantlist=True):
                    dicts_to_combine.append(data)

        return [combine(*dicts_to_combine, recursive=recursive)]
