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
conf["cassandra"]["seed_hosts"] = os.environ["CASS_HOSTS"].split(",")
conf["zookeeper"]["hosts"] = os.environ["ZK_HOSTS"]
del conf["cloudfeeds"]
del conf["cloud_client"]
conf["converger"]["interval"] = 10
conf["converger"]["build_timeout"] = 30
conf["selfheal"]["interval"] = 20
conf["terminator"]["cf_cap_url"] = os.environ["CF_CAP_URL"]
conf["terminator"]["interval"] = 10

print(json.dumps(conf, indent=2))
