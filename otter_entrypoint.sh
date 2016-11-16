#!/bin/bash

IDENTITY_URL=${IDENTITY_URL:-"http://localhost:8900/v2.0"}
# Only one seed supported
CASS_SEED_HOSTS=${CASS_SEED_HOSTS:-"tcp:localhost:9168"}
ZK_HOSTS=${ZK_HOSTS:-"localhost:2181"}

jq ".identity.url=\"${IDENTITY_URL}\" | .identity.admin_url=\"${IDENTITY_URL}\" |
   del(.cloudfeeds) | .cassandra.seed_hosts=[\"${CASS_SEED_HOSTS}\"] | 
   .zookeeper.hosts=\"${ZK_HOSTS}\"" config.example.json > /etc/otter.json

exec "$@"
