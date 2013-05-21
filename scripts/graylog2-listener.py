#!/usr/bin/env python
"""
Intercept, filter, and prettify Graylog messages.

For example:
python graylog2-listener.py
python graylog2-listener.py --pretty
python graylog2-listener.py --filter reach.twisted*
python graylog2-listener.py --filter reach.twisted.account_status --pretty
"""


import zlib
import socket
import json
import argparse
import fnmatch

parser = argparse.ArgumentParser(
    description='Intercept, filter, and prettify Graylog messages')
parser.add_argument(
    '--pretty',
    dest='pretty',
    action='store_true',
    default=False,
    help='Pretty print the output')
parser.add_argument(
    '--filter',
    nargs="*",
    dest='filter',
    default=[],
    help='Filter by facility, supports UNIX-like glob syntax')

args = parser.parse_args()


def matches(s):
    for p in args.filter:
        if fnmatch.fnmatch(s, p):
            return True
    return False

# define server properties
host = ''
port = 12201
size = 8192

print "graylog2 dummy listening on %s" % (port)

# configure server socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((host, port))

try:
    while True:
        data, address = sock.recvfrom(size)
        entry = zlib.decompress(data)
        if args.pretty or args.filter:
            decoded = json.loads(entry)
        if args.filter and not matches(decoded['facility']):
            continue

        if args.pretty:
            print json.dumps(decoded, indent=4)
        else:
            print entry
finally:
    sock.close()
