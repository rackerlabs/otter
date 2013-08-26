#!/bin/bash

GIT_SHA=$(git rev-parse --short HEAD)

docker rmi `docker images | grep none | awk '{print $3}'`
docker rm `docker ps -a -q`

# Build java
docker build -t java docker/java

# Build cassandra
docker build -t cassandra docker/cassandra

# Build otter/base
docker build -t otter/base docker/base

# Build otter
docker build -t otter:$GIT_SHA .

# Build cloudcafe
# This sucks because cloudcafe sucks
# Docker can't build things from directories higher than the Dockerfile
# and a directory can only have one Dockerfile
cd docker/cloudcafe
rm -rf autoscale_cloudcafe autoscale_cloudroast
cp -r autoscale_cloudcafe docker/cloudcafe
cp -r autoscale_cloudroast docker/cloudcafe
# Update the CloudCafe config based on environment variables
python update_cc_config.py
docker build -t otter/cloudcafe:$GIT_SHA .
rm -rf autoscale_cloudcafe autoscale_cloudroast preprod.config

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
UNIT_TESTS=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter:$GIT_SHA /bin/bash -c "cd /opt/otter; make unit")

OTTER_CID=$(docker run -d -t -e OTTER_INTERFACE=eth0 -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter:$GIT_SHA)
OTTER_IP=$(docker inspect $OTTER_CID | grep IPAddress | cut -d '"' -f 4)

# Run CloudCafe tests
CC_FUNCTIONAL_TESTS=$(docker run -d -t -e OTTER_IP=$OTTER_IP otter/cloudcafe:$GIT_SHA)

UNIT_EXIT=$(docker wait $UNIT_TESTS)
docker logs $UNIT_TESTS
CC_FUNCTIONAL_EXIT=$(docker wait $CC_FUNCTIONAL_TESTS)
docker logs $CC_TESTS

# SHUT.IT.DOWN.
docker stop $OTTER_CID
docker stop $CASSANDRA_CID
docker rmi otter:$GIT_SHA
docker rmi otter/cloudcafe:$GIT_SHA

echo "Unit tests exited $UNIT_EXIT"
echo "CloudCafe tests exited $CC_EXIT"
if [[ $UNIT_EXIT -ne 0 ]] || [[ $CC_EXIT -ne 0 ]]; then
    exit 1
fi
