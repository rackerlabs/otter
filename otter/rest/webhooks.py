"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the webhooks associated with a particular scaling group's particular scaling
policy.

(/tenantId/groups/groupId/policy/policyId/webhook
/tenantId/groups/groupId/policy/policyId/webhook/webhookId)
"""

import json

# from otter.json_schema import rest_schemas
from otter.rest.decorators import fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_autoscale_links


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks',
    methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def list_webhooks(request, tenantId, groupId, policyId):
    """
    Get a list of all webhooks (capability URL) associated with a particular
    scaling policy. This data is returned in the body of the response in JSON
    format.

    Example response::

        {
            "webhooks": [
                {
                    "id":"{webhookId1}",
                    "metadata": {
                        "notes": "this is for Alice"
                    },
                    "links": [
                        {
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId1}",
                            "rel": "self"
                        },
                        {
                            "href": ".../{groupId1}/policy/{policyId1}/webhooks/{webhookId1}",
                            "rel": "bookmark"
                        },
                        {
                            "href": ".../execute/{capability_hash1},
                            "rel": "capability"
                        }
                    ]
                },
                {
                    "id":"{webhookId2}",
                    "metadata": {
                        "notes": "this is for Bob"
                    },
                    "links": [
                        {
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId2}",
                            "rel": "self"
                        },
                        {
                            "href": ".../{groupId1}/policy/{policyId1}/webhooks/{webhookId2}",
                            "rel": "bookmark"
                        },
                        {
                            "href": ".../execute/{capability_hash2},
                            "rel": "capability"
                        }
                    ]
                }
            ],
            "webhooks_links": []
        }
    """
    # see otter.json_schema.model_schemas.view_webhook and
    # otter.json_schema.model_schemas.webhook_list to look at what the data
    # from the model implementation should look like
    def format_webhooks(webhook_dict):
        webhook_list = []
        for webhook_uuid, webhook_item in webhook_dict.iteritems():
            webhook_item['id'] = webhook_uuid
            webhook_item['links'] = get_autoscale_links(
                tenantId, groupId, policyId, webhook_uuid,
                webhook_item['capabilityURL'])
            del webhook_item['capabilityURL']
            webhook_list.append(webhook_item)

        return {
            'webhooks': webhook_list,
            "webhooks_links": []
        }

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.list_webhooks(policyId)
    deferred.addCallback(format_webhooks)
    deferred.addCallback(json.dumps)
    return deferred
