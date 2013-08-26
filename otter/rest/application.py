"""
Contains the actual Klein app and base route handlers for the REST service.
"""
from functools import partial

from twisted.web.server import Request

from klein import Klein

from otter.rest.configs import OtterConfig, OtterLaunch
from otter.rest.groups import OtterGroups
from otter.rest.policies import OtterPolicies
from otter.rest.webhooks import OtterExecute, OtterWebhooks
from otter.rest.base import BaseApp


Request.defaultContentType = 'application/json'

class Otter(BaseApp):
    """
    Otter holds the Klein app and routes for the REST service.
    """
    app = Klein()

    def __init__(self, store=None, *args, **kwargs):
        self.app.route = partial(self.app.route, strict_slashes=False)
        super(Otter, self).__init__(store, *args, **kwargs)

    @app.route('/')
    def base(self, request):
        """
        base root route.

        :returns: Empty string
        """
        return ''

    @app.route('/v1.0/<string:tenant_id>/groups', branch=True)
    def groups(self, request, tenant_id):
        """
        /v1.0/<tenantId>/groups and subroutes delegated to OtterGroups.
        """
        return OtterGroups(tenant_id, self.store).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/config')
    def config(self, request, tenant_id, group_id):
        return OtterConfig(tenant_id, group_id, self.store).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/launch')
    def launch(self, request, tenant_id, group_id):
        return OtterLaunch(tenant_id, group_id, self.store).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/policies', branch=True)
    def policies(self, request, tenant_id, group_id):
        return OtterPolicies(tenant_id, group_id, self.store).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/webhooks', branch=True)
    def webhooks(self, request, tenant_id, group_id):
        return OtterWebhooks(tenant_id, group_id, self.store).app.resource()

    @app.route('/v1.0/execute/<string:capability_version>/<string:capability_hash>/')
    def execute(self, request, capability_version, capability_hash):
        """
        """
        return OtterExecute(capability_version, capability_hash,
                            self.store).app.resource()
