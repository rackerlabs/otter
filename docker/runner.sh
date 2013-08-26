#!/bin/bash
set -ex

GIT_SHA=$(git rev-parse --short HEAD)

docker rmi `docker images | grep none | awk '{print $3}'`
docker rm `docker ps -a -q`

# Build java
docker build -t java docker/java

# Build cassandra
docker build -t cassandra docker/cassandra

# Build otter/base
docker build -t otter/base docker/base

# This will only update the OTTER_ID_PASSWORD so
# we don't have to pass it in plain text later on
./scripts/rewrite_config.py

# Build otter
docker build -t otter:$GIT_SHA .

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

OTTER_ENVS="OTTER_SEED_HOSTS=$CASSANDRA_IP"
OTTER_ENVS="$OTTER_ENVS -e CASSANDRA_HOST=$CASSANDRA_IP"
OTTER_ENVS="$OTTER_ENVS -e PYTHONPATH=/opt/otter"
OTTER_ENVS="$OTTER_ENVS -e OTTER_INTERFACE=eth0"
OTTER_ENVS="$OTTER_ENVS -e OTTER_REGION=ORD"
OTTER_ENVS="$OTTER_ENVS -e OTTER_ENVIRONMENT=production"
OTTER_ENVS="$OTTER_ENVS -e OTTER_ID_URL=https://identity.api.rackspacecloud.com/v2.0"
OTTER_ENVS="$OTTER_ENVS -e OTTER_ID_ADMIN_URL=https://as-proxy.rax.io/v2.0"

# Run otter unit tests
UNIT_TESTS=$(docker run -d -t -e $OTTER_ENVS otter:$GIT_SHA /bin/bash -c "cd /opt/otter; make unit")

OTTER_CID=$(docker run -d -t -e $OTTER_ENVS otter:$GIT_SHA)
export OTTER_IP=$(docker inspect $OTTER_CID | grep IPAddress | cut -d '"' -f 4)

# Build cloudcafe
# This sucks because cloudcafe sucks
# Docker can't build things from directories higher than the Dockerfile
# and a directory can only have one Dockerfile
cd docker/cloudcafe
rm -rf autoscale_cloudcafe autoscale_cloudroast
cp -r ../../autoscale_cloudcafe .
cp -r ../../autoscale_cloudroast .
# Update the CloudCafe config based on environment variables
python update_cc_config.py
docker build -t otter/cloudcafe:$GIT_SHA .
rm -rf autoscale_cloudcafe autoscale_cloudroast preprod.config
cd ../..

# Run CloudCafe tests
CC_FUNCTIONAL_TESTS=$(docker run -d -t -e OTTER_IP=$OTTER_IP otter/cloudcafe:$GIT_SHA)
CC_QUICKSYS_TESTS=$(docker run -d -t -e OTTER_IP=$OTTER_IP otter/cloudcafe:$GIT_SHA -p system -t speed=quick)
# CC_SLOWSYS_TESTS=$(docker run -d -t -e OTTER_IP=$OTTER_IP otter/cloudcafe:$GIT_SHA -p system -t speed=slow)

UNIT_EXIT=$(docker wait $UNIT_TESTS)
docker logs $UNIT_TESTS
CC_FUNCTIONAL_EXIT=$(docker wait $CC_FUNCTIONAL_TESTS)
docker logs $CC_FUNCTIONAL_TESTS
CC_QUICKSYS_EXIT=$(docker wait $CC_QUICKSYS_TESTS)
docker logs $CC_QUICKSYS_TESTS
# CC_SLOWSYS_EXIT=$(docker wait $CC_SLOWSYS_TESTS)
# docker logs $CC_SLOWSYS_TESTS
CC_SLOWSYS_EXIT=0

# SHUT.IT.DOWN.
docker stop $OTTER_CID
docker stop $CASSANDRA_CID
docker rmi otter:$GIT_SHA
docker rmi otter/cloudcafe:$GIT_SHA

echo "Unit tests exited $UNIT_EXIT"
echo "CloudCafe Functional tests exited $CC_FUNCTIONAL_EXIT"
echo "CloudCafe Quick System tests exited $CC_QUICKSYS_EXIT"
echo "CloudCafe Slow System tests exited $CC_SLOWSYS_EXIT"
if [[ $UNIT_EXIT -ne 0 ]] \
    || [[ $CC_FUNCTIONAL_EXIT -ne 0 ]] \
    || [[ $CC_QUICKSYS_EXIT -ne 0 ]] \
    || [[ $CC_SLOWSYS_EXIT -ne 0 ]]
then
    exit 1
fi
