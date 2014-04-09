"""
partition.py

Wrapper to kazoo partitioning receipe. Call this with partitioning information and
this will keep printing the partiton to stdout at regural intervals. Expected to be
called by otter reactor process to partition scheduler buckets

Usage:
    python partition.py <handler> <hosts> <path> <set> <time boundary> <interval>
"""
from __future__ import print_function

import time
import sys
import json
from functools import partial

from kazoo.client import KazooClient
from kazoo.handlers.gevent import SequentialGeventHandler
from kazoo.handlers.threading import SequentialThreadingHandler


def process_partitioner(partitioner, new_partitioner):
    """
    Process partitioner by checking its state

    :param partitioner: `SetPartitioner` object
    :new_partitioner: no-arg callable that creates a new partitioner
    """
    if partitioner.allocating:
        partitioner.wait_for_acquire()
    elif partitioner.release:
        partitioner.release_set()
    elif partitioner.failed:
        partitioner = new_partitioner()
    if partitioner.acquired:
        print(json.dumps({'buckets': list(partitioner)}), file=sys.stdout)
        sys.stdout.flush()
    return partitioner


def partition(client, path, set, time_boundary, interval, running=lambda: True):
    """
    Partitions and outputs the partitoned set on stdout as json line on
    interval basis
    """
    partitioner = client.SetPartitioner(path, set, time_boundary=time_boundary)
    while running():
        partitioner = process_partitioner(
            partitioner, partial(client.SetPartitioner, path, set,
                                 time_boundary=time_boundary))
        if partitioner.acquired:
            time.sleep(interval)


def main(args):
    """
    Start partition process
    """
    handler, hosts = args[0:2]
    if handler == 'gevent':
        handler = SequentialGeventHandler()
    elif handler == 'thread':
        handler = SequentialThreadingHandler()
    else:
        raise ValueError('Unknown handler')
    client = KazooClient(hosts=hosts, handler=handler)
    client.start()
    path, _set, time_boundary, interval = args[2:]
    _set = set(_set.split(','))
    partition(client, path, _set, float(time_boundary), float(interval))


if __name__ == '__main__':
    main(sys.argv[1:])
