"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import copy
import json

from otter.log import log
from otter.log.formatters import AUDIT_LOG_FIELDS
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, succeeds_with, with_transaction_id
from otter.rest.errors import exception_codes
from otter.util import logging_treq as treq
from otter.util.config import config_value
from otter.util.http import append_segments, check_success


_ELASTICSEARCH_QUERY_TEMPLATE = {
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


def make_auditlog_query(tenant_id, region):
    """Make an elastic search query to fetch audit logs."""
    query = copy.deepcopy(_ELASTICSEARCH_QUERY_TEMPLATE)

    # Add the tenant id query
    tenant_query = copy.deepcopy(_TENANT_ID_TEMPLATE)
    tenant_query['fquery']['query']['field']['tenant_id']['query'] = tenant_id
    query['query']['filtered']['filter']['bool']['must'].append(tenant_query)

    # Add the region query
    region_query = copy.deepcopy(_REGION_TEMPLATE)
    region_query['fquery']['query']['field']['tenant_id']['query'] = region.lower()
    query['query']['filtered']['filter']['bool']['must'].append(region_query)

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
    def history(self, request):
        """
        returns a list of logged autoscale events
        """
        host = config_value('elasticsearch.host')
        # XXX: rockstar (12 Dec 2013) - This is only here until we actually have an
        # endpoint in config. It'd be much better to have this blow up when it's missing
        # a config.
        if not host:
            data = {}
            return json.dumps(data)

        data = make_auditlog_query(self.tenant_id, config_value('region'))
        d = treq.get(append_segments(host, '_search'), data=json.dumps(data), log=self.log)
        d.addCallback(check_success, [200])
        d.addCallback(treq.json_content)

        def build_response(body):
            events = []

            for hit in body['hits']['hits']:
                fields = hit['_source']
                event = {
                    'event_type': fields['event_type'],
                    'timestamp': fields['@timestamp'],
                    'message': fields['message'],
                    'scaling_group_id': fields['scaling_group_id'],
                    'server_id': fields['server_id']
                }
                for name in AUDIT_LOG_FIELDS.keys():
                    field = fields.get(name)
                    if field is not None:
                        event[name] = field
                events.append(event)
            return json.dumps({'events': events})
        d.addCallback(build_response)

        return d
