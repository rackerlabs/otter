#!/usr/bin/env python

r"""
Look through a directory full of otter logs (looks at files whose names start
with "@4" and a file named "current") for specified log events.  This
expects that all the logs use the non-debug otter logging format (one line per
JSON event).

Takes a sequence of key:val-regexps to search for in events.  For the purposes
of regexp matching, the value is first ``repr``-ed.

For example, if the event is::

    {
        "key1": [1, 2, 3, 4],
        "key2": {"one": [], "two": []}
    }

then an key:val-regexp of "key1:1,\s*2,\s*.+" would match, because the regexp
"1,\s*2,\s*.+" is matched against ``repr([1, 2, 3, 4])``, not ``[1, 2, 3, 4]``.

Sample usage:

python read_logs.py --directory /var/log/otter-api \
    "scaling_group_id:.*" \
    -e "otter_facility:(kazoo|otter\.silverberg|otter\.rest\.groups\..+)" \
    -e "buckets:.*" \
    -e "log_context:_LossNotifyingWrapperProtocol.*" \


The above demonstrates that we want any log event containing a scaling group
ID, whose otter facility (if present) is not kazoo, silverberg, or a particular
otter module, who doesn't have any buckets in the event, and who does not have
a "_LossNotifiyingWrapperProtocol" log context.

"""
import json
import re

from argparse import ArgumentParser
from os.path import abspath, expanduser
from sys import argv, stdout

from twisted.python.filepath import FilePath


def get_all_log_files(directory="."):
    """
    Get all the log files in the current directory sorted by modification time.
    """
    files = FilePath(abspath(expanduser(directory))).children()
    logfiles = [f for f in files if f.basename().startswith('@4') or
                f.basename() == 'current']
    sorted_logfiles = sorted(logfiles, key=lambda f: f.getModificationTime())
    return [f.path for f in sorted_logfiles]


def process_file(filename, filter_callable, previous_line=None):
    """
    Take a log filename, read each line as JSON, filter it (determines
    whether it is a relevant log, as per ``filter_callable``) and print
    all the relevant logs.
    """
    with open(filename) as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = re.sub("^\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}\.\d+ \{", "{",
                      line, flags=re.M)
        event = None
        if i == 0 and previous_line:
            try:
                event = json.loads(previous_line + line)
            except Exception:
                pass

        if event is None:
            try:
                event = json.loads(line)
            except Exception:
                if i == len(lines) - 1:
                    return line

        if event is not None and filter_callable(event):
            stdout.write('\n')
            json.dump(event, stdout, indent=2)
            stdout.write('\n')


def run(args):
    """
    Parse command line arguments and search files.
    """
    parser = ArgumentParser(description='read and filter logs')
    parser.add_argument(
        'keyvals', type=str, nargs='*',
        help='Keys and regex values to match against in the form of '
             '"key:valregex"')
    parser.add_argument(
        '-e', dest='excludes', default=[], type=str, nargs='*',
        help='Keys and regex values to negatively match against in the form '
             'of "key:valregex" - succeeds if the key doesn\'t exist, or if '
             'the key exists but the regex doesn\'t match.')
    parser.add_argument('--directory', dest='directory', default='.',
                        help="The path to the directory containing logs.")

    options = parser.parse_args(args)
    keyvals = [keyval.split(':', 1) for keyval in options.keyvals]
    keyvals = [(k, re.compile(v)) for k, v in keyvals]

    nkeyvals = [nkeyval.split(':', 1) for nkeyval in options.excludes]
    nkeyvals = [(k, re.compile(v)) for k, v in nkeyvals]

    def filter_callable(event):
        return (
            all([event.get(k) and regexp.search(repr(event[k]))
                 for k, regexp in keyvals]) and
            all([k not in event or regexp.search(repr(event[k])) is None
                 for k, regexp in nkeyvals]))

    logfiles = get_all_log_files(options.directory)
    prev = None
    for filename in logfiles:
        prev = process_file(filename, filter_callable, prev)


if __name__ == "__main__":
    run(argv[1:])
