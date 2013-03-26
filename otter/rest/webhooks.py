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
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_autoscale_links, transaction_id
from otter.models.interface import UnrecognizedCapabilityError

from otter import controller


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
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/',
    methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def list_webhooks(request, log, tenantId, groupId, policyId):
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
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId1}/",
                            "rel": "self"
                        },
                        {
                            "href": ".../execute/1/{capability_hash1}/,
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
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId2}/",
                            "rel": "self"
                        },
                        {
                            "href": ".../execute/1/{capability_hash2}/,
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

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.list_webhooks(policyId)
    deferred.addCallback(format_webhooks)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/',
    methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(rest_schemas.create_webhooks_request)
def create_webhooks(request, log, tenantId, groupId, policyId, data):
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
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId1}/",
                            "rel": "self"
                        },
                        {
                            "href": ".../execute/1/{capability_hash1}/,
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
                            "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId2}/",
                            "rel": "self"
                        },
                        {
                            "href": ".../execute/1/{capability_hash2}/,
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

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.create_webhooks(policyId, data)
    deferred.addCallback(format_webhooks_and_send_redirect)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/<string:webhookId>/',
    methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def get_webhook(request, log, tenantId, groupId, policyId, webhookId):
    """
    Get a webhook which has a name, some arbitrary metdata, and a capability
    URL.  This data is returned in the body of the response in JSON format.

    Example response::

        {
            "webhook": {
                "id":"{webhookId}",
                "name": "webhook name",
                "metadata": {},
                "links": [
                    {
                        "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId}/",
                        "rel": "self"
                    },
                    {
                        "href": ".../execute/1/{capability_hash2},
                        "rel": "capability"
                    }
                ]
            }
        }
    """
    def format_one_webhook(webhook_model):
        result = _format_webhook(webhookId, webhook_model,
                                 tenantId, groupId, policyId)
        return {'webhook': result}

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.get_webhook(policyId, webhookId)
    deferred.addCallback(format_one_webhook)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/<string:webhookId>/',
    methods=['PUT'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(webhook)
def update_webhook(request, log, tenantId, groupId, policyId, webhookId, data):
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
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.update_webhook(policyId, webhookId, data)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/webhooks/<string:webhookId>/',
    methods=['DELETE'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def delete_webhook(request, log, tenantId, groupId, policyId, webhookId):
    """
    Deletes a particular webhook.
    If successful, no response body will be returned.
    """
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.delete_webhook(policyId, webhookId)
    return deferred


@app.route(
    '/execute/<string:capability_version>/<string:capability_hash>/',
    methods=['POST'])
@with_transaction_id()
@fails_with({})  # This will allow us to surface internal server error only.
@succeeds_with(202)
def execute_webhook(request, log, capability_version, capability_hash):
    """
    Execute a scaling policy based the capability hash.
    This returns a 202 in all cases except internal server error,
    and does not wait for execution to finish.
    """
    store = get_store()

    d = store.webhook_info_by_hash(log, capability_hash)

    def lookup_group(info):
        (tenant_id, group_id, _policy_id) = info
        group = store.get_scaling_group(log, tenant_id, group_id)
        return (info, group)

    d.addCallback(lookup_group)

    def lookup_policy((info, group)):
        (_tenant_id, _group_id, policy_id) = info
        return group.get_policy(policy_id).addCallback(lambda policy: (group, policy))

    d.addCallback(lookup_policy)

    def execute_policy((group, policy)):
        controller.maybe_execute_scaling_policy(log, transaction_id(request), group, policy)

    d.addCallback(execute_policy)

    def log_unrecognized_cap(failure):
        exc = failure.trap(UnrecognizedCapabilityError)
        log.fields(capability_hash=capability_hash,
                   capability_version=capability_version).warning(repr(exc))

    d.addErrback(log_unrecognized_cap)

    return d
