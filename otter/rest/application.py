"""
Contains the actual Klein app and base route handlers for the REST service.
"""
from twisted.web.server import Request

from otter.rest.decorators import with_transaction_id
from otter.rest.otterapp import OtterApp
from otter.rest.configs import OtterConfig, OtterLaunch
from otter.rest.groups import OtterGroups
from otter.rest.policies import OtterPolicies
from otter.rest.webhooks import OtterExecute, OtterWebhooks

Request.defaultContentType = 'application/json'


class Otter(object):
    """
    Otter holds the Klein app and routes for the REST service.
    """
    app = OtterApp()

    def __init__(self, store):
        self.store = store

    @app.route('/')
    def base(self, request):
        """
        base root route.

        :returns: Empty string
        """
        return ''

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/config/')
    def config(self, request, tenant_id, group_id):
        """
        config route handled by OtterConfig
        """
        return OtterConfig(self.store, tenant_id, group_id).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/launch/')
    def launch(self, request, tenant_id, group_id):
        """
        launch route handled by OtterLaunch
        """
        return OtterLaunch(self.store, tenant_id, group_id).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/policies/'
               '<string:policy_id>/webhooks/', branch=True)
    def webhooks(self, request, tenant_id, group_id, policy_id):
        """
        webhook routes handled by OtterWebhooks
        """
        return OtterWebhooks(self.store, tenant_id, group_id, policy_id).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/<string:group_id>/policies/', branch=True)
    @with_transaction_id()
    def policies(self, request, log, tenant_id, group_id):
        """
        policies routes handled by OtterPolicies
        """
        return OtterPolicies(self.store, log, tenant_id, group_id).app.resource()

    @app.route('/v1.0/<string:tenant_id>/groups/', branch=True)
    @with_transaction_id()
    def groups(self, request, log, tenant_id):
        """
        group routes delegated to OtterGroups.
        """
        return OtterGroups(self.store, log, tenant_id).app.resource()

    @app.route('/v1.0/execute/<string:capability_version>/<string:capability_hash>/')
    @with_transaction_id()
    def execute(self, request, log, capability_version, capability_hash):
        """
        execute route handled by OtterExecute
        """
        return OtterExecute(self.store, log, capability_version,
                            capability_hash).app.resource()
