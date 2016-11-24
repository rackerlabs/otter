#!/bin/bash

set -e

export IDENTITY_URL=${IDENTITY_URL:-"http://localhost:8900/v2.0"}
export CASS_HOSTS=${CASS_HOSTS:-"tcp:localhost:9160"}
export ZK_HOSTS=${ZK_HOSTS:-"localhost:2181"}

cust_conf.py config.example.json > /etc/otter.json

# init CASS schema and ZK nodes if needed
if [ -n "$BOOTSTRAP" ]
then
    CASS_HOST=$(extr_host_port.py cass host ${CASS_HOSTS})
    CASS_PORT=$(extr_host_port.py cass port ${CASS_HOSTS})
    ZK_HOST=$(extr_host_port.py zk host ${ZK_HOSTS})
    ZK_PORT=$(extr_host_port.py zk port ${ZK_HOSTS})
    dockerize -wait tcp://${CASS_HOST}:${CASS_PORT} -wait tcp://${ZK_HOST}:${ZK_PORT} -timeout 60s
    load_zk.py ${ZK_HOST}
    load_cql.py /otterapp/schema/setup \
		--ban-unsafe \
		--outfile /otterapp/schema/setup-dev.cql \
		--replication 1 \
		--keyspace otter \
		--host ${CASS_HOST} \
		--port ${CASS_PORT}
fi

exec "$@"
