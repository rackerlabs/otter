#!/bin/bash

set -e

export IDENTITY_URL=${IDENTITY_URL:-"http://localhost:8900/v2.0"}
export CASS_HOSTS=${CASS_HOSTS:-"tcp:localhost:9160"}
export ZK_HOSTS=${ZK_HOSTS:-"localhost:2181"}
export URL_ROOT=${URL_ROOT:-"http://localhost:9000"}

cust_conf.py config.example.json > /etc/otter.json

# init CASS schema and ZK nodes if needed
if [ -n "$BOOTSTRAP" ]
then
    # Assuming only one CASS host is there in "tcp:host:port" form and one
    # ZK host is there in "host:port" form
    CASS_HOST=$(echo $CASS_HOSTS | cut -d ":" -f 2)
    CASS_PORT=$(echo $CASS_HOSTS | cut -d ":" -f 3)
    dockerize -wait tcp://${CASS_HOST}:${CASS_PORT} -wait tcp://${ZK_HOSTS} -timeout 60s
    load_zk.py ${ZK_HOSTS}
    load_cql.py /otterapp/schema/setup \
		--ban-unsafe \
		--outfile /otterapp/schema/setup-dev.cql \
		--replication 1 \
		--keyspace otter \
		--host ${CASS_HOST} \
		--port ${CASS_PORT}
fi

exec "$@"
