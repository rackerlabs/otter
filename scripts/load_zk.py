#!/usr/bin/env python

import sys
from kazoo.client import KazooClient


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
    "/convergence-partitioner"
]

for node in nodes_to_create:
    create_or_ignore(client, node)
