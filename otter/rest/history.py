"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import json

from otter.log import log
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, succeeds_with, with_transaction_id
from otter.rest.errors import exception_codes


class OtterHistory(object):
    """
    Rest endpoints for returning audit logs.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id):
        self.log = log.bind(system='otter.log.history',
                            tenant_id=tenant_id)

        self.store = store
        self.tenant_id = tenant_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def history(self, request):
        """
        returns a list of logged autoscale events
        """
        data = {}
        return json.dumps(data)
