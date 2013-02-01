"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the webhooks associated with a particular scaling group's particular scaling
policy.

(/tenantId/groups/groupId/policy/policyId/webhook
 /tenantId/groups/groupId/policy/policyId/webhook/webhookId)
"""

import json

from otter.json_schema.group_schemas import webhook
from otter.json_schema import rest_schemas
from otter.rest.decorators import fails_with, succeeds_with, validate_body
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_autoscale_links


def _format_webhook(webhook_id, webhook_model, tenant_id, group_id, policy_id):
    """
    Take a webhook format that looks like
    :class:`otter.json_schema.model_schemas.view_webhook` and format it to
    instead look like :class:`otter.json_schema.rest_schemas.view_webhook`
    """
    webhook_model['id'] = webhook_id
    webhook_model['links'] = get_autoscale_links(
        tenant_id, group_id=group_id, policy_id=policy_id,
        webhook_id=webhook_id,
        capability_hash=webhook_model['capability']['hash'],
        capability_version=webhook_model['capability']['version'])
    del webhook_model['capability']
    return webhook_model


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
                    "name": "alice",
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
                            "href": ".../execute/1/{capability_hash1},
                            "rel": "capability"
                        }
                    ]
                },
                {
                    "id":"{webhookId2}",
                    "name": "alice",
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
                            "href": ".../execute/1/{capability_hash2},
                            "rel": "capability"
                        }
                    ]
                }
            ],
            "webhooks_links": []
        }
    """
    def format_webhooks(webhook_dict):
        webhook_list = []
        for webhook_id, webhook_model in webhook_dict.iteritems():
            webhook_list.append(
                _format_webhook(webhook_id, webhook_model, tenantId, groupId,
                                policyId))

        return {
            'webhooks': webhook_list,
            "webhooks_links": []
        }

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.list_webhooks(policyId)
    deferred.addCallback(format_webhooks)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks',
    methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(rest_schemas.create_webhooks_request)
def create_webhooks(request, tenantId, groupId, policyId, data):
    """
    Create one or many new webhooks associated with a particular scaling policy.
    Webhooks may (but do not need to) include some arbitrary medata, and must
    include a name.

    The response header will point to the list webhooks endpoint.
    An array of webhooks is provided in the request body in JSON format.

    Example request::

        [
            {
                "name": "alice",
                "metadata": {
                    "notes": "this is for Alice"
                }
            },
            {
                "name": "bob"
            }
        ]


    Example response::

        {
            "webhooks": [
                {
                    "id":"{webhookId1}",
                    "alice",
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
                            "href": ".../execute/1/{capability_hash1},
                            "rel": "capability"
                        }
                    ]
                },
                {
                    "id":"{webhookId2}",
                    "name": "bob",
                    "metadata": {},
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
                            "href": ".../execute/1/{capability_hash2},
                            "rel": "capability"
                        }
                    ]
                }
            ]
        }
    """
    def format_webhooks_and_send_redirect(webhook_dict):
        request.setHeader(
            "Location",
            get_autoscale_links(tenantId, groupId, policyId, "", format=None)
        )

        webhook_list = []
        for webhook_id, webhook_model in webhook_dict.iteritems():
            webhook_list.append(
                _format_webhook(webhook_id, webhook_model, tenantId, groupId,
                                policyId))

        return {'webhooks': webhook_list}

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.create_webhooks(policyId, data)
    deferred.addCallback(format_webhooks_and_send_redirect)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/<string:webhookId>',
    methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(webhook)
def update_webhook(request, tenantId, groupId, policyId, webhookId, data):
    """
    Update a particular webhook.
    A webhook may (but do not need to) include some arbitrary medata, and must
    include a name.
    If successful, no response body will be returned.

    Example request::

        {
            "name": "alice",
            "metadata": {
                "notes": "this is for Alice"
            }
        }
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.update_webhook(policyId, webhookId, data)
    return deferred
