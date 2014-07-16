"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import json

from otter.log import log
from otter.log.formatters import AUDIT_LOG_FIELDS
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, paginatable, succeeds_with, with_transaction_id
from otter.rest.errors import exception_codes
from otter.util import logging_treq as treq
from otter.util.http import append_segments, check_success, get_collection_links


def make_auditlog_query(tenant_id, region, limit, marker=None):
    """Make an elastic search query to fetch audit logs."""
    return {
        "size": limit,
        "query": {
            "filtered": {
                "filter": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "from": "now-30d",
                                        "to": marker or "now"
                                    }
                                }
                            },
                            {
                                "term": {"audit_log": True}
                            },
                            {
                                "term": {"tenant_id": tenant_id.strip()}
                            },
                            {
                                "term": {"tags": region.lower().strip()}
                            }
                        ]
                    }
                }
            }
        },
        "sort": [{"@timestamp": {'order': 'desc'}}]
    }


def next_marker_by_timestamp(collection, limit, marker):
    """
    Returns the next marker, which is the timestamp of the last item in the
    collection.

    To be used in :func:`otter.util.http.get_collection_links` as the
    ``next_marker`` callable, which is why there are 3 parameters, one of which
    is not used (because :func:`otter.util.http.get_collection_links` always
    calls the callable with these 3 parameters).

    :param collection: the collection to be paginated
    :type collection: iterable

    :param limit: the limit on the collection
    :param marker: the current marker used to obtain this collection - not used
        in this implementation, but accepted as per the contract in
        :func:`otter.util.http.get_collection_links`

    :return: the next marker that would be used to fetch the next collection,
        based on the last item's timestamp.  This assumes the collection is
        sorted by timestamp.
    """
    return collection[:limit][-1]['timestamp']


class OtterHistory(object):
    """
    Rest endpoints for returning audit logs.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, region, es_host=None, _treq=None):
        self.log = log.bind(system='otter.log.history',
                            tenant_id=tenant_id)

        self.store = store
        self.tenant_id = tenant_id
        self.region = region
        self.es_host = es_host
        self.treq = _treq or treq

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    @paginatable
    def history(self, request, paginate):
        """
        returns a list of logged autoscale events
        """
        if self.es_host is None:
            raise NotImplementedError(
                "Access to audit log history is not yet implemented")

        data = make_auditlog_query(self.tenant_id, self.region, **paginate)

        d = self.treq.get(append_segments(self.es_host, '_search'),
                          data=json.dumps(data), log=self.log)
        d.addCallback(check_success, [200])
        d.addCallback(self.treq.json_content)

        def build_response(body):
            events = []

            for hit in body['hits']['hits']:
                fields = hit['_source']
                event = {'timestamp': fields['@timestamp']}
                for name in AUDIT_LOG_FIELDS.keys():
                    field = fields.get(name)
                    if field is not None:
                        event[name] = field
                events.append(event)

            links = get_collection_links(
                events, request.uri, 'self',
                limit=paginate.get('limit'),
                marker=paginate.get('marker'),
                next_marker=next_marker_by_timestamp)
            return json.dumps({'events': events, 'events_links': links})
        d.addCallback(build_response)

        return d
