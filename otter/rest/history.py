"""
rest endpoints that return the audit log

/v1.0/tenant_id/history
"""
import copy
import json

import treq

from otter.log import log
from otter.rest.otterapp import OtterApp
from otter.rest.decorators import fails_with, succeeds_with, with_transaction_id
from otter.rest.errors import exception_codes
from otter.util.config import config_value
from otter.util.http import check_success


_ELASTICSEARCH_QUERY_TEMPLATE = {
    "query": {
        "filtered": {
            "query": {
                "bool": {
                    "should": [
                        {"query_string": {"query": "is_error:false"}},
                        {"query_string": {"query": "is_error:true"}}
                    ]
                }
            },
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


def make_auditlog_query(tenant_id):
    """Make an elastic search query to fetch audit logs."""
    query = copy.deepcopy(_ELASTICSEARCH_QUERY_TEMPLATE)
    tenant_query = copy.deepcopy(_TENANT_ID_TEMPLATE)
    tenant_query['fquery']['query']['field']['tenant_id']['query'] = tenant_id
    query['query']['filtered']['filter']['bool']['must'].append(tenant_query)

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

        data = make_auditlog_query(self.tenant_id)
        d = treq.get('{0}/_search'.format(host), json.dumps(data))
        d.addCallback(check_success, [200])

        def get_body(response):

            return treq.content(response)
        d.addCallback(get_body)

        def build_response(body):
            events = []

            response = json.loads(body)
            for hit in response['hits']['hits']:
                fields = hit['_source']['@fields']
                event = {
                    'event_type': fields['event_type'],
                    'timestamp': fields['@timestamp'],
                    'message': hit['_source']['message'],
                    'policy_id': fields['policy_id'],
                    'scaling_group_id': fields['scaling_group_id'],
                    'server_id': fields['server_id']
                }
                events.append(event)
            return json.dumps({'events': events})
        d.addCallback(build_response)

        return d
