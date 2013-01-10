"""
Resource script for the autoscale API
"""

import os
import sys

from tryfer.http import TracingWrapperResource
from tryfer.tracers import push_tracer, DebugTracer, EndAnnotationTracer

from otter.rest.application import root

# Add the debug tracer, if in debug environment
if os.getenv("OTTER_ENV", None) == "debug":
    push_tracer(EndAnnotationTracer(DebugTracer(sys.stdout)))


resource = TracingWrapperResource(root, service_name='otter')
