from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os

from ansible import constants as C
from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    ''' Adds parent host of failed dynamic_hosts to retry file '''

    CALLBACK_VERSION = 2.0
    CALLBACK_NAME = 'retry'

    def v2_playbook_on_start(self, playbook):
        self.playbook_path = os.path.join(playbook._basedir, playbook._file_name)

    def v2_playbook_on_stats(self, stats):
        hosts = list(set([host.split('->')[0].strip() for host in stats.failures.keys() if '->' in host]))

        if not len(hosts) or not C.RETRY_FILES_ENABLED:
            return

        # modeled after ansible/ansible: lib/ansible/executor/playbook_executor.py
        if C.RETRY_FILES_SAVE_PATH:
            basedir = C.RETRY_FILES_SAVE_PATH
        elif self.playbook_path:
            basedir = os.path.dirname(os.path.abspath(self.playbook_path))
        else:
            basedir = '~/'

        (retry_name, _) = os.path.splitext(os.path.basename(self.playbook_path))
        filename = os.path.join(basedir, "%s.retry" % retry_name)

        hosts.append('localhost')
        with open(filename, 'a') as f:
            f.write('\n'.join(hosts))
