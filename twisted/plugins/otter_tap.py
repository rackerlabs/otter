"""
Otter twisted application plugins for the various services.
"""

from twisted.application.service import ServiceMaker

OtterAPI = ServiceMaker(
    "Otter API endpoint.",
    "otter.tap.api",
    "Handle API requests",
    "otter-api"
)
