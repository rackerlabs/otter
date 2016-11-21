#!/bin/bash

set -e

IDENTITY_URL=${IDENTITY_URL:-"http://localhost:8900/v2.0"}
# Only one seed supported for now
CASS_SEED_HOST=${CASS_SEED_HOST:-"tcp:localhost:9168"}
ZK_HOST=${ZK_HOST:-"localhost:2181"}

jq ".identity.url=\"${IDENTITY_URL}\" | .identity.admin_url=\"${IDENTITY_URL}\" |
   del(.cloudfeeds) | .cassandra.seed_hosts=[\"${CASS_SEED_HOSTS}\"] | 
   .zookeeper.hosts=\"${ZK_HOSTS}\"" config.example.json > /etc/otter.json

# init CASS schema and ZK nodes if needed
if [ -v ${BOOTSTRAP} ]
then
    source /zkshellvenv/bin/activate
    cat << EOF | zk-shell --run-from-stdin ${ZK_HOST}
    create /groups/divergent d false false true
    create /locks d
    create /selfheallock d
    create /scheduler_partition d
    create /convergence-partitioner
    EOF


fi


exec "$@"
