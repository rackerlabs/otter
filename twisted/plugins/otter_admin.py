"""
Otter twisted application plugins for the various services.
"""

from twisted.application.service import ServiceMaker

OtterAdminAPI = ServiceMaker(
    "Otter Admin API endpoint.",
    "otter.tap.admin",
    "Handle admin API requests",
    "otter-admin-api"
)
