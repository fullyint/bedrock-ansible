# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
'''
Lookup plugin to union a list of lists by prioritized host pattern
========================================================================================

The `union_for_host` lookup plugin offers a means of assembling a list from sublists
indicated to be applicable to different host patterns. The return value is a union of
the sublists whose key/pattern matches the current host.

The `union_for_host` lookup plugin expects each variable submitted to be a list
of dictionaries, where each dictionary key is a host pattern and the value is a list.
Lists are submitted to the Ansible `union` filter.
For info about host patterns, see http://docs.ansible.com/ansible/intro_patterns.html

---
# example variable listing sublists to union:
something_to_union:
  - all:
      - some value
      - other value
  - web:&production:
      - yet another value

another_thing_to_union:
  - db:&production:
      - some db value

# basic union -- basic plugin usage
union_result: "{{ lookup('union_for_host', something_to_union) }}"
  # Yields the following for a host that is in both the `web` and `production` groups:
  #  union_result:
  #    - some value
  #    - other value
  #    - yet another value

# possible to union multiple vars
union_result_multi: "{{ lookup('union_for_host', something_to_union, another_thing_to_union) }}"

# evaluates current `inventory_hostname` against host pattern (default), but accepts `host` override via kwarg
union_result_based_on_other_host: "{{ lookup('union_for_host', something_to_union, host='some_other_host') }}"

'''
from ansible.errors import AnsibleError
from ansible.module_utils.six import iteritems
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.filter.mathstuff import union
from ansible.plugins.lookup import LookupBase
from ansible.template import Templar


class LookupModule(LookupBase):
    ''' Union lists whose key/pattern matches current host '''

    def check_type(self, item, item_type):
        if not isinstance(item, item_type):
            raise AnsibleError('\n\n`union_for_host` expects each variable submitted to be a list of\n'
                    'dictionaries, where each dictionary key is a host pattern\n'
                    'and the value is a list. For info about host patterns,\n'
                    'see http://docs.ansible.com/ansible/intro_patterns.html\n\n'
                    'Example variable format:\n\n'
                    'something_to_union:\n'
                    '  - all:\n'
                    '      - some value\n'
                    '      - other value\n'
                    '  - web:&production:\n'
                    '      - yet another value\n\n'
                    'Here is the problematic item that caused the error:\n\n{}\n'.format(repr(item)))

    def run(self, terms, variables=None, wantlist=True, **kwargs):
        lookup = Templar(variables=variables, loader=DataLoader())._lookup
        host = kwargs.pop('host', variables['inventory_hostname'])
        result = []

        for term in LookupBase._flatten(terms):
            if term is None:
                continue

            self.check_type(term, dict)

            for pattern,value in term.iteritems():
                if value is None:
                    continue

                self.check_type(value, list)
                if host in lookup('inventory_hostnames', pattern, wantlist=True):
                    result = union(result, value)

        return [result]
