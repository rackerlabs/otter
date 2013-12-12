"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import json

from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from otter.log import log
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, succeeds_with, with_transaction_id
from otter.rest.errors import exception_codes
from otter.util.config import config_value


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
        host = config_value('elasticsearch.host')
        # XXX: rockstar (12 Dec 2013) - This is only here until we actually have an
        # endpoint in config. It'd be much better to have this blow up when it's missing
        # a config.
        if not host:
            data = {}
            return json.dumps(data)

        # TODO: filter by tenant id.
        agent = Agent(reactor)
        d = agent.request('GET', host, Headers({'User-Agent': ['otter']}), None)

        def handle_response(response):
            request.write(response)
            request.finish()
        d.addCallback(handle_response)

        return d
