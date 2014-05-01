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
from otter.util.config import config_value
from otter.util.http import (
    append_segments, check_success, get_collection_links, next_marker_by_offset)


def make_auditlog_query(tenant_id, region, marker=0, limit=0):
    """Make an elastic search query to fetch audit logs."""

    return {
        "from": marker,
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
                                        "to": "now"
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
    @paginatable
    def history(self, request, paginate):
        """
        returns a list of logged autoscale events
        """
        host = config_value('elasticsearch.host')
        if not host:
            raise NotImplementedError(
                "Access to audit log history is not yet implemented")

        data = make_auditlog_query(self.tenant_id, config_value('region'), **paginate)
        d = treq.get(append_segments(host, '_search'), data=json.dumps(data), log=self.log)
        d.addCallback(check_success, [200])
        d.addCallback(treq.json_content)

        def build_response(body):
            events = []

            if 'marker' in paginate:
                try:
                    paginate['marker'] = int(paginate['marker'])
                except:
                    pass

            for hit in body['hits']['hits']:
                fields = hit['_source']
                event = {'timestamp': fields['@timestamp']}
                for name in AUDIT_LOG_FIELDS.keys():
                    field = fields.get(name)
                    if field is not None:
                        event[name] = field
                events.append(event)
            links = get_collection_links(
                events, request.uri, 'self', limit=paginate.get('limit'),
                marker=paginate.get('marker'), next_marker=next_marker_by_offset)
            return json.dumps({'events': events, 'events_links': links})
        d.addCallback(build_response)

        return d
