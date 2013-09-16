"""
rest endpoints that return group limits

(/v1.0/tenant_id/limits
"""
import json
from lxml import etree

from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, succeeds_with
from otter.rest.errors import exception_codes


class OtterLimits(object):
    """
    REST endpoints for returning group limits.
    """
    app = OtterApp()

    def __init__(self, store, log, tenant_id):
        self.store = store
        self.log = log
        self.tenant_id = tenant_id

    @app.route('/', methods=['GET'])
    @fails_with(exception_codes)
    @succeeds_with(200)
    def list_limits(self, request):
        """
        returns application limits
        """
        data = {
            "limits": {
                "absolute": {
                    "maxGroups": 1000,
                    "maxPoliciesPerGroup": 1000,
                    "maxWebhooksPerPolicy": 1000,
                }
            }
        }

        accept = request.getHeader("accept")

        if accept and 'xml' in accept:
            url = "http://docs.openstack.org/common/api/v1.0"

            xml = etree.Element("limits", xmlns=url)
            absolute = etree.SubElement(xml, "absolute")

            for key, val in data['limits']['absolute'].iteritems():
                etree.SubElement(absolute, "limit", name=key, value=str(val))

            request.setHeader("Content-Type", "application/xml")
            return etree.tostring(xml, encoding="UTF-8", xml_declaration=True)

        return json.dumps(data)
