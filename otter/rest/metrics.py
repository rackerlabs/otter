"""
Classes and functions for managing metrics around Otter.
"""
import json

from otter.log import log
from otter.rest.decorators import (fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.otterapp import OtterApp


class OtterMetrics(object):
    """
    Endpoints for getting metrics out of Otter.
    """
    app = OtterApp()

    def __init__(self, store):
        """
        Initialize OtterMetrics with a data store and log.
        """
        self.log = log.bind(system='otter.rest.metrics')
        self.store = store

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def list_metrics(self, request):
        """
        Get a list of metrics from cassandra.

        Example response::

            {
                "metrics": [
                    {
                        "id": "otter.metrics.scaling_groups",
                        "value": 3207,
                        "time": 13120497123
                    },
                    {
                        "id": "otter.metrics.scaling_policies",
                        "value": 2790,
                        "time": 13139792343
                    }
                ]
            }
        """
        deferred = self.store.get_metrics(self.log)
        deferred.addCallback(lambda metrics: json.dumps({'metrics': metrics}))
        return deferred
