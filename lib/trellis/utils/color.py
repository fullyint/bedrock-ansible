# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re
import textwrap

from ansible import constants as C
from ansible.compat.six import iteritems
from ansible.utils.color import codeCodes, stringc

def none(value):
    return value if value.lower() != 'none' else None

def load_configs(obj):
    # Retain these constants' definitions until min required Ansible version includes...
    # https://github.com/bcoca/ansible/commit/d3deb24#diff-b77962b6b54a830ec373de0602918318R271
    C.COLOR_CHANGED = C.get_config(C.p, 'colors', 'ok', 'ANSIBLE_COLOR_CHANGED', 'yellow')
    C.COLOR_ERROR = C.get_config(C.p, 'colors', 'error', 'ANSIBLE_COLOR_ERROR', 'red')
    C.COLOR_OK = C.get_config(C.p, 'colors', 'ok', 'ANSIBLE_COLOR_OK', 'green')
    C.COLOR_SKIP = C.get_config(C.p, 'colors', 'skip', 'ANSIBLE_COLOR_SKIP', 'cyan')
    C.COLOR_WARN = C.get_config(C.p, 'colors', 'warn', 'ANSIBLE_COLOR_WARN', 'bright purple')

    obj.color_code = C.get_config(C.p, 'trellis_output', 'color_code', 'TRELLIS_COLOR_CODE', 'normal')
    obj.color_code_block = C.get_config(C.p, 'trellis_output', 'color_code_block', 'TRELLIS_COLOR_CODE_BLOCK', C.COLOR_CHANGED)
    obj.color_default = C.get_config(C.p, 'trellis_output', 'color_default', 'TRELLIS_COLOR_DEFAULT', C.COLOR_SKIP)
    obj.color_error = C.get_config(C.p, 'trellis_output', 'color_error', 'TRELLIS_COLOR_ERROR', C.COLOR_ERROR)
    obj.color_hr = C.get_config(C.p, 'trellis_output', 'color_hr', 'TRELLIS_COLOR_HR', 'bright gray')
    obj.color_ok = C.get_config(C.p, 'trellis_output', 'color_ok', 'TRELLIS_COLOR_OK', C.COLOR_OK)
    obj.color_system_info = C.get_config(C.p, 'trellis_output', 'color_system_info', 'TRELLIS_COLOR_SYSTEM_INFO', 'bright gray')
    obj.color_warn = C.get_config(C.p, 'trellis_output', 'color_warn', 'TRELLIS_COLOR_WARN', C.COLOR_WARN)

def wrap_text(chunk, wrap_width):
    # Extract ANSI escape codes
    pattern = r'(\033\[.*?m|\033\[0m)'
    codes = re.findall(pattern, chunk)

    # Achieve more accurate wrap width by replacing multi-character ANSI escape codes with single character placeholder
    sub = None
    sub_candidates = ['~', '^', '|', '#', '@', '$', '&', '*', '?', '!', ';', '+', '=', '<', '>', '%', '-', '9', '8']
    for candidate in sub_candidates:
        if candidate not in chunk:
            sub = candidate
            break
    chunk = re.sub(pattern, sub, chunk)

    # Wrap text
    chunk = '\n'.join([textwrap.fill(line, wrap_width, replace_whitespace=False)
                       for line in chunk.splitlines()])

    # Replace placeholders with original ANSI escape codes
    for code in codes:
        chunk = chunk.replace(sub, code, 1)

    return chunk

def split_color_strings(obj, chunk, color_1, delimiter, color_2, code_block):
    if none(color_2) is not None:
        for n, snippet in enumerate(re.split(delimiter, chunk, re.I)):
            if n % 2 is 0:
                snippet = colorize(obj, snippet, color_1, code_block)
            else:
                snippet = colorize(obj, snippet, color_2, code_block)
            chunk = snippet if n is 0 else ''.join([chunk, snippet])
    else:
        chunk = ''.join(re.split(delimiter, chunk, re.I))
        chunk = colorize(obj, chunk, color_1, code_block)

    return chunk

def colorize(obj, chunk, color, code_block=False):
    # If chunk still has color tags, send chunk off to be split further
    color_tags = {
        r'</?default>': obj.color_default,
        r'</?error>': obj.color_error,
        r'</?ok>': obj.color_ok,
        r'</?warn>': obj.color_warn,
        }

    for tag, color_2 in color_tags.iteritems():
        if re.search(tag, chunk, re.I):
            chunk = split_color_strings(obj, chunk, color, tag, color_2, code_block)

    if '`' in chunk and not code_block and none(obj.color_code) is not None:
        chunk = split_color_strings(obj, chunk, color, '`', obj.color_code, code_block)

    if re.search(r'</?bold>', chunk, re.I):
        color_bold = color
        if not color.startswith(('black', 'normal', 'white', 'bright')):
            color_bold = 'bright {0}'.format(color)
        elif color == 'dark gray':
            color_bold = 'bright gray'
        chunk = split_color_strings(obj, chunk, color, r'</?bold>', color_bold, code_block)

    # Apply color
    chunk = stringc(chunk, color)

    return chunk

# Apply colors to msg and add textwrap to non-code blocks
def split_and_colorize(obj, msg, failed):
    if msg.strip() == '':
        return msg

    color = none(obj.color_error) if failed else none(obj.color_default)
    for i, chunk in enumerate(msg.split('\n```\n')):
        if chunk.strip() == '':
            continue

        # Process non-code block, then code block
        if i % 2 is 0:
            chunk = colorize(obj, chunk.strip(), color)
            chunk = wrap_text(chunk, obj.wrap_width)
        else:
            chunk = colorize(obj, chunk, obj.color_code_block, code_block=True)

        assembled = '\n'.join([chunk, '']) if i is 0 else '\n'.join([assembled, chunk, ''])

    return assembled

def normal(color):
    return color if color.lower() != 'none' else 'normal'

def load_vars(obj, play):
    play.vars['ansible_colors'] = ''.join([stringc(color.ljust(int(obj.wrap_width/3)), color)
                                           for color in codeCodes.keys()])
    play.vars['color_settings'] = '\n'.join([
        stringc('color_code: {0}'.format(obj.color_code), normal(obj.color_code)),
        stringc('color_code_block: {0}'.format(obj.color_code_block), normal(obj.color_code_block)),
        stringc('color_default: {0}'.format(obj.color_default), normal(obj.color_default)),
        stringc('color_error: {0}'.format(obj.color_error), normal(obj.color_error)),
        stringc('color_hr: {0}'.format(obj.color_hr), normal(obj.color_hr)),
        stringc('color_ok: {0}'.format(obj.color_ok), normal(obj.color_ok)),
        stringc('color_system_info: {0}'.format(obj.color_system_info), normal(obj.color_system_info)),
        stringc('color_warn: {0}'.format(obj.color_warn), normal(obj.color_warn)),
        ])
