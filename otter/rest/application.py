"""
Contains the actual Klein app and base route handlers for the REST service.
"""
from functools import partial

from klein import Klein

from otter.rest.groups import OtterGroups
from otter.rest.webhooks import OtterExecute
from otter.rest.base import BaseApp


class Otter(BaseApp):
    """
    Otter holds the Klein app and routes for the REST service.
    """
    root = Klein()
    app = Klein()

    def __init__(self, store, *args, **kwargs):
        self.root.route = partial(self.root.route, strict_slashes=False)
        super(Otter, self).__init__(store, *args, **kwargs)

    @root.route('/')
    def base(self, request):
        """
        base root route.

        :returns: Empty string
        """
        request.setHeaders('Content-Type', 'application/json')
        return ''

    @root.route('/v1.0', branch=True)
    def v1_0(self, request):
        """
        Version 1.0 root route

        :returns: All requests handled by app, not root.
        """
        return self.app.resource()

    @app.route('/<string:tenant_id>/groups', branch=True)
    def groups(self, request, tenant_id):
        """
        /v1.0/<tenantId>/groups and subroutes delegated to OtterGroups.
        """
        return OtterGroups(tenant_id, self.store).app.resource()

    @app.route('/execute/<string:capability_version>/<string:capability_hash>/')
    def execute(self, request, capability_version, capability_hash):
        """
        """
        return OtterExecute(capability_version, capability_hash,
                            self.store).app.resource()
