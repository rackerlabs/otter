"""
Autoscale REST endpoints having to do with administration of otter.

(/metrics)
"""

import json

from klein import Klein

from otter.util import timestamp

from otter.models.mock import MockAdmin


class OtterAdmin(object):
    """
    The admin application is a RESTful interface to the backend of
    otter.
    """
    app = Klein()

    def __init__(self, store=None):
        if store is not None:
            self.store = store
        else:
            self.store = MockAdmin()

    @app.route('/', methods=['GET'])
    def root(self, request):
        """
        Root response for admin API.
        """
        return ''

    @app.route('/metrics', methods=['GET'])
    def list_metrics(self, request, log=None):
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
        def format_data(results):
            """
            :param results: Results from running the collect_metrics call.

            :return: Correctly formatted data to be jsonified.
            """
            metrics = []
            for key, value in results.iteritems():
                metrics.append(dict(
                    id="otter.metrics.{0}".format(key),
                    value=value,
                    time=timestamp.now()))

            return {'metrics': metrics}

        deferred = self.store.get_metrics(log)
        deferred.addCallback(format_data)
        deferred.addCallback(json.dumps)
        return deferred
