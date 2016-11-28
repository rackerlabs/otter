#!/bin/bash

set -e
dockerize -wait http://otter:9000/health -wait http://mimic:8900 -timeout 30s
exec cafe-runner autoscale "$@"
