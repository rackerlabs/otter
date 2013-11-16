"""
Script that tails an otter log and filters out only JSON events that contain
a particular key
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
    Listens to a file, reads json events, and filters out the audit log
    """
    delimiter = '\n'

    def __init__(self, key="audit_log"):
        self.event_buffer = []
        self.key = key

    def connectionMade(self):
        print("Filtering for events containing '{key}'".format(key=self.key))

    def connectionLost(self, reason):
        print("\n")
        reason.trap(ConnectionDone, ConnectionLost)

    def emit(self, data):
        print(data)

    def json_filter(self, event_str):
        event = json.loads(event_str)
        if self.key in event:
            return event

    def lineReceived(self, line):
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
    parser = argparse.ArgumentParser('audit log filter')
    parser.add_argument('filepath', help="path to the file to tail")
    parser.add_argument('--key', help="json key to filter on", required=False,
                        default='audit_log')
    return parser.parse_args()


def connect_to_tail(reactor, filepath, key):
    endpoint = endpoints.ProcessEndpoint(reactor, 'tail',
                                         args=('tail', '-f', filepath))
    protocol = JsonEventReceiver(key)
    endpoints.connectProtocol(endpoint, protocol)
    return Deferred()


if __name__ == "__main__":
    args = parse_args()
    react(connect_to_tail, (args.filepath, args.key))
