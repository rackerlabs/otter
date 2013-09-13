#!/usr/bin/env python

"""
Write a bunch of hosts to the hosts file
"""

import os

to_write = os.environ.get('HOSTS_TO_WRITE')

if to_write is not None:
    entries = [entry.split('=', 1) for entry in to_write.split(';')]
    text = '\n'.join(['\t'.join([entry[1], entry[0]]) for entry in entries])

    with open('/etc/hosts', 'ab') as f:
        f.write('\n# custom entries\n')
        f.write(text)
