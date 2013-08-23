
# Build cassandra
docker build -t cassandra docker/cassandra

# Build otter/base
docker build -t otter/base docker/base

# Build otter
docker build -t otter .

# Build cloudcafe
# This sucks because cloudcafe sucks
rm -rf docker/cloudcafe/autoscale_cloudcafe docker/cloudcafe/autoscale_cloudroast
cp -r autoscale_cloudcafe docker/cloudcafe
cp -r autoscale_cloudroast docker/cloudcafe
docker build -t otter/cloudcafe docker/cloudcafe

# Setup CloudCafe environment variables
CC_ENVS="-e OTTER_IP=$OTTER_IP"
CC_ENVS="$CC_ENVS -e CC_USER_PASSWORD=$CC_USER_PASSWORD"
CC_ENVS="$CC_ENVS -e CC_USER_API_KEY=$CC_USER_API_KEY"
CC_ENVS="$CC_ENVS -e CC_NON_AS_PASSWORD=$CC_NON_AS_PASSWORD"

# Run Test containers
CASSANDRA_CID=$(docker run -d -t -h cassandra -e MAX_HEAP_SIZE=512M -e HEAP_NEWSIZE=256M cassandra)
CASSANDRA_IP=$(docker inspect $CASSANDRA_CID | grep IPAddress | cut -d '"' -f 4)
OTTER_CID=$(docker run -d -t -e CASSANDRA_HOST=$CASSANDRA_IP -e CASSANDRA_IP=$CASSANDRA_IP otter /bin/bash)
OTTER_IP=$(docker inspect $OTTER_CID | grep IPAddress | cut -d '"' -f 4)
