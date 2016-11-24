#!/usr/bin/env python

# Extract host and port part from zk or cass hostnames
# Usage: python extr_host_port.py cass host tcp:hname1:port

import sys

_type = sys.argv[1]
part = sys.argv[2]
# Cass names are like "tcp:host:port,tcp:host2:port2,..." and ZK hosts are like
# "host1:port1,host2:port2,..."
hostnames = sys.argv[3]

hostname = hostnames.split()[0]
if _type == "zk":
    if part == "host":
        print hostname.split(":")[0]
    if part == "port":
        print hostname.split(":")[1]
elif _type == "cass":
    if part == "host":
        print hostname.split(":")[1]
    if part == "port":
        print hostname.split(":")[2]
