#!/usr/bin/env python

from os import environ
import simplejson as json

with open("config.json") as f:
    config_json = json.load(f)

config_json['region'] = environ.get('OTTER_REGION', 'ORD')
config_json['environment'] = environ.get('OTTER_ENVIRONMENT', 'staging')
config_json['url_root'] = environ.get('URL_ROOT', 'http://127.0.0.1:9000')
config_json['cassandra']['seed_hosts'] = environ.get(
    'OTTER_SEED_HOSTS', "tcp:127.0.0.1:9160"
).split(";")
config_json['identity']['password'] = environ.get('OTTER_ID_PASSWORD', 'REPLACE_ME')

with open("config.json", 'w') as f:
    f.write(json.dumps(config_json, sort_keys=True, indent=2))
