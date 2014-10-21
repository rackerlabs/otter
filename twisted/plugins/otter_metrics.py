"""
Otter twisted application plugins for the various services.
"""

from twisted.application.service import ServiceMaker

OtterMetrics = ServiceMaker(
    "Otter Metrics Collector",
    "otter.metrics",
    "Collects metrics for a region on an interval basis",
    "otter-metrics"
)

