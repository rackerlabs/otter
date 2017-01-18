#!/usr/bin/env python

"""
Create all the necessary znodes in Zookeeper to get otter up and running.
Takes ZK hosts as argument.
"""

import sys

from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError


def create_or_ignore(client, path):
    try:
        client.create(path, makepath=True)
    except NodeExistsError:
        pass


host = sys.argv[1]
client = KazooClient(hosts=host)
client.start()

nodes_to_create = [
    "/groups/divergent",
    "/locks",
    "/selfheallock",
    "/scheduler_partition",
    "/convergence-partitioner",
    "/terminator/prev_params",
    "/terminator/lock"
]

for node in nodes_to_create:
    create_or_ignore(client, node)
