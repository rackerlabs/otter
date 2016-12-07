#!/usr/bin/env python

from __future__ import print_function

"""
This is used by otter docker container to customize otter's config based on env
variables. Pass in a sample config file to it.
"""

import json
import os
import sys

conf = json.load(open(sys.argv[1]))
conf["url_root"] = os.environ["URL_ROOT"]
conf["identity"]["url"] = os.environ["IDENTITY_URL"]
conf["identity"]["admin_url"] = os.environ["IDENTITY_URL"]
del conf["cloudfeeds"]
conf["cassandra"]["seed_hosts"] = os.environ["CASS_HOSTS"].split(",")
conf["zookeeper"]["hosts"] = os.environ["ZK_HOSTS"]

print(json.dumps(conf, indent=2))
