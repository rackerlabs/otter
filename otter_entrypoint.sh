#!/bin/bash

IDENTITY_URL=${IDENTITY_URL:-"http://localhost:8900/v2.0"}
CASS_SEED_HOSTS=${CASS_SEED_HOSTS:-"[tcp:localhost:9168]"}
ZK_HOSTS=${ZK_HOSTS:-"localhost:2181"}

#echo ".identity.url=$IDENTITY_URL | .identity.admin_url=$IDENTITY_URL" config.example.json 
jq ".identity.url=$IDENTITY_URL" config.example.json | jq ".identity.admin_url=$IDENTITY_URL" 
   # jq "del(.cloudfeeds) | .cassandra.seed_hosts=$CASS_SEED_HOSTS" | \
   # jq ".zookeeper.hosts=$ZK_HOSTS" > config.json
#cat config.json

#exec "$@"
