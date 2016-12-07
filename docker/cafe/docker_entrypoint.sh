#!/bin/bash

set -e

OTTER_ROOT=${OTTER_ROOT:-"http://otter:9000"}
IDENTITY_ROOT=${IDENTITY_ROOT:-"http://mimic:8900"}
CAFE_DIR=/root/.cloudcafe/configs/autoscale

sed -i -e "s,OTTER_ROOT,$OTTER_ROOT,g" $CAFE_DIR/dev-convergence.config $CAFE_DIR/dev-worker.config
sed -i -e "s,IDENTITY_ROOT,$IDENTITY_ROOT,g" $CAFE_DIR/dev-convergence.config $CAFE_DIR/dev-worker.config

if [ -n "$WAIT" ]; then
    dockerize -wait $OTTER_ROOT/health -wait $IDENTITY_ROOT  -timeout 30s
fi

exec cafe-runner autoscale "$@"
