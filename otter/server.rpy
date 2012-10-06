"""Null"""

import os
import sys
from tryfer.http import TracingWrapperResource
from tryfer.tracers import push_tracer, DebugTracer, EndAnnotationTracer

import otter.scaling_groups

# Add the debug tracer.
push_tracer(EndAnnotationTracer(DebugTracer(sys.stdout)))

resource = TracingWrapperResource(otter.scaling_groups.root, service_name='otter')

