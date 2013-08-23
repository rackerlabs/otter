
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

# Run otter unit tests
docker run -i -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter /bin/bash -c "cd /opt/otter; make unit"

OTTER_CID=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e OTTER_SEED_HOSTS="tcp:$CASSANDRA_IP:9160" -e PYTHONPATH=/opt/otter otter)
OTTER_IP=$(docker inspect $OTTER_CID | grep IPAddress | cut -d '"' -f 4)

# Setup CloudCafe environment variables
CC_ENVS="OTTER_IP=$OTTER_IP"
CC_ENVS="$CC_ENVS -e CC_USER_PASSWORD=$CC_USER_PASSWORD"
CC_ENVS="$CC_ENVS -e CC_USER_API_KEY=$CC_USER_API_KEY"
CC_ENVS="$CC_ENVS -e CC_NON_AS_PASSWORD=$CC_NON_AS_PASSWORD"

# Run CloudCafe tests
docker run -i -t -e $CC_ENVS otter/cloudcafe

# SHUT.IT.DOWN.
docker stop $OTTER_CID
docker stop $CASSANDRA_CID
