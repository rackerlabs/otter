"""
Autoscale REST endpoints having to do with administration of Otter.
"""
from otter.rest.metrics import OtterMetrics
from otter.rest.otterapp import OtterApp


class OtterAdmin(object):
    """
    OtterAdmin is a RESTful interface to manage and otter.
    """
    app = OtterApp()

    def __init__(self, store):
        """
        Initialize OtterAdmin.
        """
        self.store = store

    @app.route('/', methods=['GET'])
    def root(self, request):
        """
        Root response for OtterAdmin.
        """
        return ''

    @app.route('/metrics/', branch=True)
    def metrics(self, request):
        """
        Routes related to metrics are delegated to OtterMetrics.
        """
        return OtterMetrics(self.store).app.resource()
