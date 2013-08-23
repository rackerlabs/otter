#!/bin/bash

docker rmi `docker images | grep none | awk '{print $3}'`
docker rm `docker ps -a -q`

# Build java
docker build -t java docker/java

# Build cassandra
docker build -t cassandra docker/cassandra

# Build otter/base
docker build -t otter/base docker/base

# Build otter
docker build -t otter .

# Build cloudcafe
# This sucks because cloudcafe sucks
# Docker can't build things from directories higher than the Dockerfile
# and a directory can only have one Dockerfile
rm -rf docker/cloudcafe/autoscale_cloudcafe docker/cloudcafe/autoscale_cloudroast
cp -r autoscale_cloudcafe docker/cloudcafe
cp -r autoscale_cloudroast docker/cloudcafe
docker build -t otter/cloudcafe docker/cloudcafe

# Run Test containers
CASSANDRA_CID=$(docker run -d -t -h cassandra -e MAX_HEAP_SIZE=512M -e HEAP_NEWSIZE=256M cassandra)
CASSANDRA_IP=$(docker inspect $CASSANDRA_CID | grep IPAddress | cut -d '"' -f 4)

# This is the best way I could determine that Cassandra is up and functional
# nc -z always returns 0 due to the nat port existing
for (( i = 0; i < 10; i++ )); do
    sleep 1
    echo "Attempting to load schema"
    LDS=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter /bin/bash -c "cd /opt/otter; make load-dev-schema")
    CASSANDRA_RUNNING=$(docker wait $LDS)
    if [[ $CASSANDRA_RUNNING -eq 0 ]]; then
        echo "Schema loaded"
        break
    fi
done

# Run otter unit tests
UNIT_TESTS=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter /bin/bash -c "cd /opt/otter; make unit")

OTTER_CID=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter)
OTTER_IP=$(docker inspect $OTTER_CID | grep IPAddress | cut -d '"' -f 4)

# Setup CloudCafe environment variables
CC_ENVS="OTTER_IP=$OTTER_IP"
CC_ENVS="$CC_ENVS -e CC_USER_PASSWORD=$CC_USER_PASSWORD"
CC_ENVS="$CC_ENVS -e CC_USER_API_KEY=$CC_USER_API_KEY"
CC_ENVS="$CC_ENVS -e CC_NON_AS_PASSWORD=$CC_NON_AS_PASSWORD"

# Run CloudCafe tests
CC_TESTS=$(docker run -d -t -e $CC_ENVS otter/cloudcafe)

docker wait $UNIT_TESTS
docker logs $UNIT_TESTS
docker wait $CC_TESTS
docker logs $CC_TESTS

# SHUT.IT.DOWN.
docker stop $OTTER_CID
docker stop $CASSANDRA_CID
