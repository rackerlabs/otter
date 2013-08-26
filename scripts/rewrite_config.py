#!/usr/bin/env python

"""
Rewrite the config.json file based on environment variables to make
docker and CloudCafe run correctly
"""

from os import environ
from sys import exit
from subprocess import check_output, CalledProcessError
import json


def get_ip_for_interface(iface):
    if iface is None:
        return None
    try:
        cmd = " | ".join([
            "ip addr show {0}".format(otter_interface),
            "grep -o 'inet [0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+'",
            "grep -o [0-9].*"
        ])
        return check_output(cmd, shell=True)
    except CalledProcessError:
        return None

with open("config.json") as f:
    config_json = json.load(f)

# These options can only be set up sensibly inside the docker container
if environ.get('DOCKER'):
    seed_hosts = environ.get(
        'OTTER_SEED_HOSTS', ['127.0.0.1']
    ).split(";")
    seed_hosts = ["tcp:%s:9160" % x for x in seed_hosts]
    config_json['cassandra']['seed_hosts'] = seed_hosts

    # If OTTER_INTERFACE is specified URL_ROOT will be that interface's
    # address:9000
    otter_interface = environ.get('OTTER_INTERFACE', None)
    ipaddress = get_ip_for_interface(otter_interface)
    if ipaddress:
        config_json['url_root'] = "http://{0}:9000".format(ipaddress.strip())
    else:
        config_json['url_root'] = environ.get('OTTER_URL_ROOT', 'http://127.0.0.1:9000')

    config_json['region'] = environ.get('OTTER_REGION', 'ORD')
    config_json['environment'] = environ.get('OTTER_ENVIRONMENT', 'staging')

    config_json['identity']['url'] = environ.get(
        'OTTER_ID_URL',
        'https://staging.identity.api.rackspacecloud.com/v2.0'
    )
    config_json['identity']['admin_url'] = environ.get(
        'OTTER_ID_ADMIN_URL',
        'https://staging.identity.api.rackspacecloud.com/v2.0'
    )
# These options should be set before the docker build
else:
    try:
        config_json['identity']['password'] = environ.get('OTTER_ID_PASSWORD')
    except KeyError:
        print("Must set OTTER_ID_PASSWORD environment variable")
        exit(1)

with open("config.json", 'w') as f:
    f.write(json.dumps(config_json, sort_keys=True, indent=2))
