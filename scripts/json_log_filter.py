"""
Script that tails an otter log and filters out only JSON events that contain
a particular key

Usage:
python json_log_filter.py <file to tail> [--key=<some json field name>]

Works like tail, but will only emit the json event logs that have the key
<some json field name>.  By default, only emits logs that have the key
"audit_log"

Works with otter logs whether they're debug or not.
"""

from __future__ import print_function

import argparse
import json

from twisted.internet import endpoints
from twisted.internet.error import ConnectionDone, ConnectionLost
from twisted.internet.defer import Deferred
from twisted.protocols.basic import LineReceiver
from twisted.internet.task import react

# http://twistedmatrix.com/trac/ticket/6606
endpoints._ProcessEndpointTransport.disconnecting = False


class JsonEventReceiver(LineReceiver):
    """
    Listens to a file, reads json events, and filters out the audit log.
    """
    delimiter = '\n'

    def __init__(self, key="audit_log"):
        self.event_buffer = []
        self.key = key

    def connectionMade(self):
        """
        When the tail process is openned
        """
        print("Filtering for events containing '{key}'".format(key=self.key))

    def connectionLost(self, reason):
        """
        Print a newline, otherwise ignore.
        """
        print("\n")
        reason.trap(ConnectionDone, ConnectionLost)

    def emit(self, data):
        """
        Actually just print
        """
        print(data)

    def json_filter(self, event_str):
        """
        Loads a string as JSON - if it works, only return it if it has the key
        """
        event = json.loads(event_str)
        if self.key in event:
            return event

    def lineReceived(self, line):
        """
        Processes log lines - they can either be all on one line, or split
        across multiple lines as is produced by observer_factory_debug
        """
        results = line.split(" ", 1)

        if len(results) < 2:
            self.emit(line)
            return

        timestamp, logline = results

        # is it a full json event?
        try:
            event = self.json_filter(logline)
        except:
            # nope, parse it line by line
            self.event_buffer.append(logline)
            if logline.strip() == '}':
                data, self.event_buffer = self.event_buffer, []
                merged = "\n".join(data)
                try:
                    event = self.json_filter(merged)
                except:
                    pass
                else:
                    if event:
                        self.emit(merged)
        else:
            # full json contains the key - dump it in a human readable format
            if event:
                stringified = json.dumps(event, indent=2)
                formatted = "\n".join([('    ' * 4) + l for l in
                                       stringified.split('\n')])
                self.emit(timestamp + "\n" + formatted)


def parse_args():
    """
    Parse command line arguments for filename and key to look for
    """
    parser = argparse.ArgumentParser("json_log_filter.py")
    parser.add_argument('filepath', help="path to the file to tail")
    parser.add_argument('--key', help="json key to filter on", required=False,
                        default='audit_log')
    return parser.parse_args()


def connect_to_tail(reactor, filepath, key):
    """
    Spawns "tail" process and hooks up the protocol
    """
    endpoint = endpoints.ProcessEndpoint(reactor, 'tail',
                                         args=('tail', '-f', filepath))
    protocol = JsonEventReceiver(key)
    endpoints.connectProtocol(endpoint, protocol)
    return Deferred()


if __name__ == "__main__":
    args = parse_args()
    react(connect_to_tail, (args.filepath, args.key))
