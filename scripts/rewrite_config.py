#!/usr/bin/env python

"""
Rewrite the config.json file based on environment variables to make
docker and CloudCafe run correctly
"""

from os import environ
from subprocess import check_output, CalledProcessError
import json

with open("config.json") as f:
    config_json = json.load(f)

# If OTTER_INTERFACE is specified URL_ROOT will be that interface's
# address:9000
otter_interface = environ.get('OTTER_INTERFACE', None)
if otter_interface:
    try:
        cmd = " | ".join([
            "ip addr show {0}".format(otter_interface),
            "grep -o 'inet [0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+'",
            "grep -o [0-9].*"
        ])
        ipaddress = check_output(cmd)
    except CalledProcessError:
        ipaddress = "127.0.0.1"
    config_json['url_root'] = "http://{0}:9000".format(ipaddress)
else:
    config_json['url_root'] = environ.get('URL_ROOT', 'http://127.0.0.1:9000')

config_json['region'] = environ.get('OTTER_REGION', 'ORD')
config_json['environment'] = environ.get('OTTER_ENVIRONMENT', 'staging')
config_json['cassandra']['seed_hosts'] = environ.get(
    'OTTER_SEED_HOSTS', "tcp:127.0.0.1:9160"
).split(";")
config_json['identity']['password'] = environ.get('OTTER_ID_PASSWORD', 'REPLACE_ME')

with open("config.json", 'w') as f:
    f.write(json.dumps(config_json, sort_keys=True, indent=2))
