"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import copy
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


_ELASTICSEARCH_QUERY_TEMPLATE = {
    "from": None,
    "size": None,
    "query": {
        "filtered": {
            "filter": {
                "bool": {
                    "must": [{
                        "range": {
                            "@timestamp": {
                                "from": "now-30d",
                                "to": "now"
                            }
                        }
                    }, {
                        "fquery": {
                            "query": {
                                "field": {
                                    "audit_log": {
                                        "query": True
                                    }
                                }
                            }
                        }
                    }]
                }
            }
        }
    }
}
_TENANT_ID_TEMPLATE = {
    "fquery": {
        "query": {
            "field": {
                "tenant_id": {
                    "query": None
                }
            }
        }
    }
}
_REGION_TEMPLATE = {
    "fquery": {
        "query": {
            "field": {
                "tags": {
                    "query": None
                }
            }
        }
    }
}


def make_auditlog_query(tenant_id, region, marker=0, limit=0):
    """Make an elastic search query to fetch audit logs."""
    query = copy.deepcopy(_ELASTICSEARCH_QUERY_TEMPLATE)

    # Add the tenant id query
    tenant_query = copy.deepcopy(_TENANT_ID_TEMPLATE)
    tenant_query['fquery']['query']['field']['tenant_id']['query'] = tenant_id
    query['query']['filtered']['filter']['bool']['must'].append(tenant_query)

    # Add the region query
    region_query = copy.deepcopy(_REGION_TEMPLATE)
    region_query['fquery']['query']['field']['tags']['query'] = region.lower()
    query['query']['filtered']['filter']['bool']['must'].append(region_query)

    query['from'] = marker
    query['size'] = limit

    return query


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
