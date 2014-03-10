"""
partition.py

Wrapper to kazoo partitioning receipe. Call this with partitioning information and
this will keep printing the partiton to stdout at regural intervals. Expected to be
called by otter reactor process to partition scheduler buckets

Usage:
    python partition.py <hosts> <path> <set> <time boundary> <interval>
"""

import time
import sys
import json

from kazoo.client import KazooClient


def partition(client, path, set, time_boundary, interval):
    """
    Partitions and outputs the partitoned set on stdout as json line on
    interval basis
    """
    partitioner = client.SetPartitioner(path, set, time_boundary=time_boundary)
    while True:
        if partitioner.allocating:
            partitioner.wait_for_acquire()
        elif partitioner.release:
            partitioner.release_set()
        elif partitioner.failed:
            partitioner = client.SetPartitioner(path, set, time_boundary=time_boundary)
        elif partitioner.acquired:
            print(json.dumps({'buckets': list(partitioner)}))
            sys.stdout.flush()
            time.sleep(interval)


def main(args):
    """
    Start partition process
    """
    client = KazooClient(hosts=args[0])
    client.start()
    path, _set, time_boundary, interval = args[1:]
    _set = set(_set.split(','))
    partition(client, path, _set, float(time_boundary), float(interval))


if __name__ == '__main__':
    main(sys.argv[1:])
