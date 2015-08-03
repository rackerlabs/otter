"""
Contains the actual Klein app and base route handlers for the REST service.
"""
import json

from twisted.internet.defer import maybeDeferred
from twisted.web.server import Request

from otter.rest.groups import OtterGroups
from otter.rest.limits import OtterLimits
from otter.rest.otterapp import OtterApp
from otter.rest.webhooks import OtterExecute

from otter.util.config import config_value

Request.defaultContentType = 'application/json'


class Otter(object):
    """
    Otter holds the Klein app and routes for the REST service.
    """
    app = OtterApp()

    def __init__(self, store, region, health_check_function=None, _treq=None):
        self.store = store
        self.region = region
        self.health_check_function = health_check_function
        self.scheduler = None
        self.treq = _treq
        # Effect dispatcher for all otter intents
        self.dispatcher = None

    @app.route('/', methods=['GET'])
    def base(self, request):
        """
        base root route.

        :returns: Whatever is configured to be returned by the root
        """
        code = config_value('root.code')
        if code is not None:
            request.setResponseCode(code)

        headers = config_value('root.headers')
        if headers is not None:
            for header in headers:
                for value in headers[header]:
                    request.setHeader(str(header), str(value))

        body = config_value('root.body')
        if body is not None:
            return body

        return ''

    @app.route('/v1.0/<string:tenant_id>/groups/', branch=True)
    def groups(self, request, tenant_id):
        """
        group routes delegated to OtterGroups.
        """
        return OtterGroups(
            self.store, tenant_id, self.dispatcher).app.resource()

    @app.route('/v1.0/execute/<string:cap_version>/<string:cap_hash>/')
    def execute(self, request, cap_version, cap_hash):
        """
        execute route handled by OtterExecute
        """
        return OtterExecute(self.store, cap_version, cap_hash).app.resource()

    @app.route('/v1.0/<string:tenant_id>/limits')
    def limits(self, request, tenant_id):
        """
        return group limit maximums
        """
        return OtterLimits(self.store, tenant_id).app.resource()

    @app.route('/health', methods=['GET'])
    def health_check(self, request):
        """
        Return whether health checks succeeded
        """
        request.setHeader('X-Response-Id', 'health_check')
        if self.health_check_function:
            return self.health_check_function().addCallback(json.dumps, sort_keys=True,
                                                            indent=4)

        return json.dumps({'healthy': True})

    @app.route('/scheduler/reset', methods=['POST'])
    def scheduler_reset(self, request):
        """
        Reset the scheduler with new path
        """
        new_path = request.args.get('path')[0]
        request.setHeader('X-Response-Id', 'scheduler_reset')
        try:
            self.scheduler.reset(new_path)
        except ValueError as e:
            request.setResponseCode(400)
            return e.message
        else:
            return ''

    @app.route('/scheduler/stop', methods=['POST'])
    def scheduler_stop(self, request):
        """
        Stop the scheduler
        """
        request.setHeader('X-Response-Id', 'scheduler_stop')
        d = maybeDeferred(self.scheduler.stopService)
        return d.addCallback(lambda _: '')
