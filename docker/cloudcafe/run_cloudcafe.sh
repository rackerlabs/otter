#!/bin/bash

PYTHONPATH=/opt/otter/autoscale_cloudcafe:/opt/otter/autoscale_cloudroast

# Replace server_endpoint IP
if [[ $OTTER_IP ]]; then
    sed -i "s/127.0.0.1/$OTTER_IP/g" $2
fi

cafe-runner "$@"
