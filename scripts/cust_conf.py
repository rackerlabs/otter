#!/usr/bin/env python

import json
import sys
import os

conf = json.load(open(sys.argv[1]))
conf["identity"]["url"] = os.environ["IDENTITY_URL"]
conf["identity"]["admin_url"] = os.environ["IDENTITY_URL"]
del conf["cloudfeeds"]
conf["cassandra"]["seed_hosts"] = os.environ["CASS_HOSTS"].split(",")
conf["zookeeper"]["hosts"] = os.environ["ZK_HOSTS"]

print json.dumps(conf, indent=2)
