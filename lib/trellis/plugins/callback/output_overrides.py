# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os.path
import sys

from ansible import constants as C
from ansible.plugins.callback.default import CallbackModule as CallbackModule_default

try:
    from trellis.plugins.callback import TrellisCallbackBase
except ImportError:
    if sys.path.append(os.path.join(os.getcwd(), 'lib')) in sys.path: raise
    sys.path.append(sys.path.append(os.path.join(os.getcwd(), 'lib')))
    from trellis.plugins.callback import TrellisCallbackBase


class CallbackModule(TrellisCallbackBase, CallbackModule_default):
    ''' Suppresses some standard Ansible output '''

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'output_overrides'

    def __init__(self):

        super(CallbackModule, self).__init__()

        # Optional configs from trellis.cfg
        self.display_skipped_tasks = C.get_config(self.cfg, 'output_general', 'display_skipped_tasks', 'TRELLIS_DISPLAY_SKIPPED_TASKS', False, boolean=True)
        self.display_skipped_items = C.get_config(self.cfg, 'output_general', 'display_skipped_items', 'TRELLIS_DISPLAY_SKIPPED_ITEMS', False, boolean=True)
        self.display_include_tasks = C.get_config(self.cfg, 'output_general', 'display_include_tasks', 'TRELLIS_DISPLAY_INCLUDE_TASKS', False, boolean=True)

    def suppress_output(self, result):
        return (self.output_custom and self._display.verbosity < 3 and
               (self.role == 'trellis' or
               self.action in ['debug', 'fail', 'assert'] and 'msg' in result._result))

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if self.suppress_output(result):
            pass
        else:
            super(CallbackModule, self).v2_runner_on_failed(result, ignore_errors)

    def v2_runner_on_ok(self, result):
        if self.suppress_output(result):
            pass
        else:
            super(CallbackModule, self).v2_runner_on_ok(result)

    def v2_runner_on_skipped(self, result):
        if not self.display_skipped_tasks and self._display.verbosity < 3:
            pass
        else:
            super(CallbackModule, self).v2_runner_on_skipped(result)

    def v2_playbook_on_task_start(self, task, is_conditional):
        if not self.display_include_tasks and task._get_parent_attribute('action') == 'include' and self._display.verbosity < 3:
            pass
        else:
            super(CallbackModule, self).v2_playbook_on_task_start(task, is_conditional)

    def v2_playbook_on_include(self, included_file):
        if not self.display_include_tasks and self._display.verbosity < 3:
            pass
        else:
            super(CallbackModule, self).v2_playbook_on_include(included_file)

    def v2_playbook_item_on_ok(self, result):
        if self.suppress_output(result):
            pass
        else:
            super(CallbackModule, self).v2_playbook_item_on_ok(result)

    def v2_playbook_item_on_failed(self, result):
        if self.suppress_output(result):
            pass
        else:
            super(CallbackModule, self).v2_playbook_item_on_failed(result)

    def v2_playbook_item_on_skipped(self, result):
        if (not self.display_skipped_items and self._display.verbosity < 3) or self.suppress_output(result):
            pass
        else:
            super(CallbackModule, self).v2_playbook_item_on_skipped(result)
