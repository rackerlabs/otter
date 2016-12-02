#!/bin/bash

set -e

OTTER_ROOT=${OTTER:-"http://otter:9000"}
IDENTITY_ROOT=${IDENTITY_ROOT:-"http://mimic:8900"}

if [ -n "$WAIT" ]; then
    dockerize -wait $OTTER_ROOT/health -wait $IDENTITY_ROOT  -timeout 30s
fi

exec cafe-runner autoscale "$@"
