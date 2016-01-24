# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os.path
import platform
import re
import sys
import textwrap

from ansible import __version__
from ansible import constants as C
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.callback import CallbackBase
from ansible.utils.color import stringc
from ansible.utils.unicode import to_unicode

try:
    from trellis.plugins.callback import TrellisCallbackBase
except ImportError:
    if sys.path.append(os.path.join(os.getcwd(), 'lib')) in sys.path: raise
    sys.path.append(sys.path.append(os.path.join(os.getcwd(), 'lib')))
    from trellis.plugins.callback import TrellisCallbackBase

# Retain these constants' definitions until min required Ansible version includes...
# https://github.com/bcoca/ansible/commit/d3deb24#diff-b77962b6b54a830ec373de0602918318R271
C.COLOR_SKIP = C.get_config(C.p, 'colors', 'skip', 'ANSIBLE_COLOR_SKIP', 'cyan')
C.COLOR_ERROR = C.get_config(C.p, 'colors', 'error', 'ANSIBLE_COLOR_ERROR', 'red')
C.COLOR_WARN = C.get_config(C.p, 'colors', 'warn', 'ANSIBLE_COLOR_WARN', 'bright purple')
C.COLOR_CHANGED = C.get_config(C.p, 'colors', 'ok', 'ANSIBLE_COLOR_CHANGED', 'yellow')
C.COLOR_OK = C.get_config(C.p, 'colors', 'ok', 'ANSIBLE_COLOR_OK', 'green')


class CallbackModule(TrellisCallbackBase, CallbackBase):
    ''' Displays Ansible output and custom messages in readable format '''

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = '90_output_format'

    def __init__(self):

        super(CallbackModule, self).__init__()

        # Configs manually defined here
        self.header_fail = '  Trellis Debug'
        self.header_ok = '  Playbook Completed Successfully'
        self.header_tips = 'Tips:'
        self.output_docs = 'To manage this output, see https://roots.io/trellis/docs/cli-output/'

        # Auto-populated variables
        self.vagrant_version = None
        self.tips = None

        # Optional configs from trellis.cfg
        self.colorize_code = C.get_config(self.cfg, 'output_custom', 'colorize_code', 'TRELLIS_COLORIZE_CODE', True, boolean=True)
        self.color_default = C.get_config(self.cfg, 'output_custom', 'color_default', 'TRELLIS_COLOR_DEFAULT', C.COLOR_SKIP)
        self.color_ok = C.get_config(self.cfg, 'output_custom', 'color_ok', 'TRELLIS_COLOR_OK', C.COLOR_OK)
        self.color_error = C.get_config(self.cfg, 'output_custom', 'color_error', 'TRELLIS_COLOR_ERROR', C.COLOR_ERROR)
        self.color_warn = C.get_config(self.cfg, 'output_custom', 'color_warn', 'TRELLIS_COLOR_WARN', C.COLOR_WARN)
        self.color_code = C.get_config(self.cfg, 'output_custom', 'color_code', 'TRELLIS_COLOR_CODE', 'normal')
        self.color_code_block = C.get_config(self.cfg, 'output_custom', 'color_code_block', 'TRELLIS_COLOR_CODE_BLOCK', C.COLOR_CHANGED)
        self.color_hr = C.get_config(self.cfg, 'output_custom', 'color_hr', 'TRELLIS_COLOR_HR', 'bright gray')
        self.color_footer = C.get_config(self.cfg, 'output_custom', 'color_footer', 'TRELLIS_COLOR_FOOTER', 'bright gray')

    def system(self):
        vagrant = ''.join([' Vagrant ', self.vagrant_version, ';']) if self.vagrant_version else ''
        return 'Ansible {0};{1} {2}'.format(__version__, vagrant, platform.system())

    # Get most recent CHANGELOG entry
    def changelog_msg(self):
        changelog_msg = ''
        changelog = os.path.join(os.getcwd(), 'CHANGELOG.md')
        if os.path.isfile(changelog):
            with open(changelog) as f:
                str = f.read(200)
            # Retrieve release number if it is most recent entry
            release = re.search(r'^###\s((?!HEAD).*)', str)
            if release is not None:
                changelog_msg = 'Trellis {0}'.format(release.group(1))
            # Retrieve most recent changelog entry
            else:
                change = re.search(r'.*\n\*\s*([^\(\n\[]+)', str)
                if change is not None:
                    changelog_msg = 'Trellis at "{0}"'.format(change.group(1).strip())
        return changelog_msg

    def wrap(self, chunk):
        # Extract ANSI escape codes
        pattern = r'(\033\[.*?m|\033\[0m)'
        codes = re.findall(pattern, chunk)
        # Replace ANSI escape codes with single character placeholder
        # to minimize the effect on wrap width had by the invisible characters in ANSI escape codes
        sub = None
        sub_candidates = ['~', '^', '|', '#', '@', '$', '&', '*', '?', '!', ';', '+', '=', '<', '>', '%', '-', '9', '8']
        for candidate in sub_candidates:
            if candidate not in chunk:
                sub = candidate
                break
        chunk = re.sub(pattern, sub, chunk)
        # Wrap text
        chunk = '\n'.join([textwrap.fill(line, self.wrap_width, replace_whitespace=False)
                           for line in chunk.splitlines()])
        # Replace the placeholders with ANSI escape codes
        for code in codes:
            chunk = chunk.replace(sub, code, 1)
        return chunk

    def colorize_defaults(self, chunk, color):
        if 'C_ERROR' in chunk:
            chunk = self.split_and_colorize(chunk, color, 'C_ERROR', self.color_error)
        elif 'C_OK' in chunk:
            chunk = self.split_and_colorize(chunk, color, 'C_OK', self.color_ok)
        elif 'C_WARN' in chunk:
            chunk = self.split_and_colorize(chunk, color, 'C_WARN', self.color_warn)
        elif 'C_BOLD' in chunk:
            color_bold = color
            if not color.startswith(('black', 'normal', 'white', 'bright')):
                color_bold = ' '.join(['bright', color])
            elif color == 'dark gray':
                color_bold = 'bright gray'
            chunk = self.split_and_colorize(chunk, color, 'C_BOLD', color_bold)
        else:
            chunk = stringc(chunk, color)
        return chunk

    def split_and_colorize(self, chunk, color_1, sep=None, color_2=None):
        if sep is None:
            chunk = self.colorize_defaults(chunk, color_1)
            return chunk
        for n, snippet in enumerate(chunk.split(sep)):
            if n % 2 is 0:
                snippet = self.colorize_defaults(snippet, color_1)
            else:
                snippet = self.colorize_defaults(snippet, color_2)
            chunk = snippet if n is 0 else ''.join([chunk, snippet])
        return chunk

    def get_output(self, result, output='', index=None):
        # Add msgs from looping tasks (e.g., tasks using `with_items`)
        if 'results' in result:
            results = (res for res in result['results'] if 'skipped' not in res)
            for i, res in enumerate(results):
                output = self.get_output(res, output, i)
            return output

        msg = ''
        error = True if 'play_error' in result or 'failed' in result or 'unreachable' in result else False

        # Only display msg if passed as arg to module or if task failed
        # (there is occasionally an undesired 'msg' value on task ok)
        if 'msg' in result and (error or self.action in ['debug', 'fail', 'assert']):
            # Pop msg out of result so ansible.plugins.default doesn't also display it
            # msg = result.pop('msg', '')
            msg = result['msg']

        if 'failed' in result:
            # Display any additional info if available
            for item in ['module_stderr', 'module_stdout', 'stderr']:
                if item in result and to_unicode(result[item]) != '':
                    msg = result[item] if msg == '' else '\n'.join([msg, result[item]])

        # Detect if name passed as param in validations/tips tasks
        has_name = self.role == 'trellis' and 'name' in result.get('item', {}) and result['item']['name'] != ''

        # Return original output if nothing to add
        if msg == '' and not has_name:
            return output

        # Dynamic color selection
        color = self.color_error if error else self.color_warn
        color_regular_text = self.color_default if has_name else color

        # Add validation/tip name
        if has_name:
            name = '{0!s} - {1}'.format(index + 1, result['item']['name'])
            if self.colorize_code:
                name = self.wrap(self.split_and_colorize(name, color, '`', self.color_code))
            else:
                name = self.wrap(stringc(name, color))
            if output != '':
                output = '\n'.join([output, '', name])
            else:
                output = '\n'.join(['', name])

        # Convert msg to unicode string because self._diplay.display() can only take strings
        # From ansible/utils/display.py --
        #   "Note: msg *must* be a unicode string to prevent UnicodeError tracebacks."
        if isinstance(msg, list):
            msg = '\n'.join([to_unicode(x) for x in msg])
        elif not isinstance(msg, unicode):
            msg = to_unicode(msg)

        if msg == '':
            return output

        # Apply colors to msg and add textwrap to non-code blocks
        for i, chunk in enumerate(msg.split('\n```\n')):
            if chunk == '':
                continue

            # Non code block text
            if i % 2 is 0:
                # Apply color
                if self.colorize_code:
                    chunk = self.split_and_colorize(chunk.strip(), color_regular_text, '`', self.color_code)
                else:
                    chunk = self.split_and_colorize(chunk.strip(), color_regular_text)
                # Apply textwrap
                chunk = self.wrap(chunk)

            # Code block - apply color (no textwrap)
            else:
                chunk = self.split_and_colorize(chunk, self.color_code_block)

            assembled = '\n'.join([chunk, '']) if i is 0 else '\n'.join([assembled, chunk, ''])

        if output != '':
            return '\n'.join([output, assembled]).lstrip()
        else:
            return assembled.lstrip()

    def display_output(self, result):
        # Retrieve output main content
        output = self.get_output(result._result)
        error = True if 'play_error' in result._result or result.is_failed() or result.is_unreachable() else False

        if self.role == 'trellis' or error:
            # Dynamic color selection
            color = self.color_error if error else self.color_warn
            header_color = color if error else self.color_ok

            # Prepare header
            hr = stringc('-' * self.wrap_width, self.color_hr)
            header = self.header_fail if error else self.header_ok
            header = stringc(self.wrap(header), header_color)
            header = '\n'.join([hr, header, hr])
            if not error:
                tips = stringc(self.wrap(self.header_tips), color)
                header = '\n'.join([header, tips])

            # Add system info to footer if task failed
            footer = ''
            if error:
                specs = '\n'.join([self.system(), self.changelog_msg()])
                specs = stringc(self.wrap(specs), self.color_footer)
                hr_small = '-' * min([len(self.system()), self.wrap_width])
                footer = '\n'.join([stringc(hr_small, self.color_hr), specs])

            # Add output docs note to footer
            output_docs = stringc(self.wrap(self.output_docs), self.color_footer)
            footer = output_docs if footer == '' else '\n'.join([footer, output_docs])

            # Add header and footer to output
            output = '\n'.join(['', header, '', output, footer, hr, '\n'])

        # Display message
        if self.task != 'trellis : Prepare tips':
            self._display.display(output)
        else:
            self.tips = output

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.display_output(result)

    def v2_runner_on_ok(self, result):
        self.display_output(result)
        if not self.display_ok_items and 'results' in result._result:
            for res in result._result['results']:
                if 'item' in res:
                    res['item'] = 'suppressed'

    def v2_runner_on_unreachable(self, result):
        self.display_output(result)

    def v2_playbook_on_start(self, playbook):
        super(CallbackModule, self).v2_playbook_on_start(playbook)
        # Print custom message added in `messages.py` callback plugin
        try:
            self.display_output(playbook)
        except AttributeError:
            pass

    def v2_playbook_on_no_hosts_matched(self):
        # Print custom message added in `messages.py` callback plugin
        try:
            self.display_output(self.play_obj)
        except AttributeError:
            pass

    def v2_playbook_on_task_start(self, task, is_conditional):
        super(CallbackModule, self).v2_playbook_on_task_start(task, is_conditional)

    def v2_playbook_on_handler_task_start(self, task):
        super(CallbackModule, self).v2_playbook_on_handler_task_start(task)

    def v2_playbook_on_play_start(self, play):
        super(CallbackModule, self).v2_playbook_on_play_start(play)
        # Check for settings overrides passed via cli --extra-vars
        self.disable_plugin_via_cli(play)
        loader = DataLoader()
        play_vars = play.get_variable_manager().get_vars(loader=loader, play=play)
        if 'vagrant_version' in play_vars:
            self.vagrant_version = play_vars['vagrant_version']
        if 'wrap_width' in play_vars:
            self.wrap_width = int(play_vars['wrap_width'])

    def v2_playbook_on_stats(self, stats):
        # Display tips here, with stats, after any handlers have run
        if not stats.failures and self.tips:
            self._display.display(self.tips.rstrip())
