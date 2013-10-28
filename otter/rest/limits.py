"""
rest endpoints that return group limits

/v1.0/tenant_id/limits
"""
import json
from lxml import etree

from otter.log import log
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import (fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.util.config import config_value


class OtterLimits(object):
    """
    REST endpoints for returning group limits.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id):
        self.log = log.bind(system='otter.log.limits',
                            tenant_id=tenant_id)
        self.store = store
        self.tenant_id = tenant_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def list_limits(self, request):
        """
        returns application limits
        """
        data = {"limits": {"absolute": config_value("limits.absolute")}}
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
