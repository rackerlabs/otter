"""
Autoscale REST endpoints having to do with editing/modifying the configuration
or launch configuration for a scaling group.

(/tenantId/autoscale/groupId/config and /tenantId/autoscale/groupId/launch)
"""

import json

from twisted.internet import defer

from otter.json_schema import scaling_group as sg_schema
from otter.rest.decorators import validate_body, fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_url_root


@app.route(('/<string:tenantId>/autoscale/<string:groupId>'
            '/policy/<string:policyId>/webhook'),
           methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_all_webhooks(request, tenantId, groupId, policyId):
    """
    Get a mapping of IDs to their respective scaling policy webhooks.
    Each webhook has a name, url, and cooldown.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
            "42fa3cb-bfb0-44c0-85fa-3cfbcbe5c257": {
                "name": "pagerduty",
                "URL":
                    "autoscale.api.rackspacecloud.com/v1.0/action/
                    d0f4c14c48ad4837905ea7520cc4af700f6433ce0985e6bb87b6b461
                    7cb944abf814bd53964ddbf55b41e5812b3afe90890c0a4db75cb043
                    67e139fd62eab2e1",
                "cooldown": 150
            },
            "b556078a-8c29-4129-9411-72580ffd0ba0": {
                "name": "maas",
                "URL":
                    "autoscale.api.rackspacecloud.com/v1.0/action/
                    db48c04dc6a93f7507b78a0dc37a535fa1f06e1a45ba138d30e3d4b4
                    d8addce944e11b6cbc3134af0d203058a40bd239766f97dbcbca5dff
                    f1e4df963414dbfe",
                "cooldown": 150
            }
        }
    """
    rec = get_store().get_all_webhooks(tenantId, groupId, policyId)
    deferred = defer.maybeDeferred(rec.view_all_webhooks)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(('/<string:tenantId>/autoscale/<string:groupId>'
            '/policy/<string:policyId>/webhook'),
           methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(sg_schema.policy)
def create_webhook(request, tenantId, groupId, policyId, data):
    """
    Create a new scaling policy webhook. Scaling policies must include a name
    and cooldown.
    The response header will point to the generated policy webhook resource.
    This data provided in the request body in JSON format.

    Example request::

        {
            "name": "the best webhook ever",
            "cooldown": 150
        }

    """

    def send_redirect(groupId, policyId, webhookId):
        request.setHeader(
            "Location",
            "{0}/{1}/autoscale/{2}/policy/{3}/webhook/{4}".format(
                get_url_root(),
                tenantId,
                groupId,
                policyId,
                webhookId
            )
        )

    rec = get_store().get_webhook(tenantId, groupId, policyId)
    deferred = defer.maybeDeferred(rec.create_webhook, data)
    deferred.addCallback(send_redirect)
    return deferred


@app.route(('/<string:tenantId>/autoscale/<string:groupId>'
            '/policy/<string:policyId>/webhook/<string:webhookId>'),
           methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_webhook(request, tenantId, groupId, policyId, webhookId):
    """
    Get information about a specific scaling policy webhook.
    Each webhook has a name, url, and cooldown.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
            "name": "pagerduty",
            "URL":
                "autoscale.api.rackspacecloud.com/v1.0/action/
                db48c04dc6a93f7507b78a0dc37a535fa1f06e1a45ba138d30e3d4b4
                d8addce944e11b6cbc3134af0d203058a40bd239766f97dbcbca5dff
                f1e4df963414dbfe",
            "cooldown": 150
        }
    """
    rec = get_store().get_webhook(tenantId, groupId, policyId, webhookId)
    deferred = defer.maybeDeferred(rec.view_webhook)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(('/<string:tenantId>/autoscale/<string:groupId>'
            '/policy/<string:policyId>/webhook/<string:webhookId>'),
           methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(sg_schema.policy)
def edit_webhook(request, tenantId, groupId, policyId, webhookId, data):
    """
    Update an existing webhook.
    WebhookIds not recognized will be ignored with accompanying data.
    URLs will be ignored if submitted, but that will not invalidate the request.
    If successful, no response body will be returned.

    Example initial state::

        {
            "name": "maas",
            "URL":
               "autoscale.api.rackspacecloud.com/v1.0/action/
               db48c04dc6a93f7507b78a0dc37a535fa1f06e1a45ba138d30e3d4b4
               d8addce944e11b6cbc3134af0d203058a40bd239766f97dbcbca5dff
               f1e4df963414dbfe",
            "cooldown": 150
        }

    Example request::

       {
            "name": "something completely different",
            "URL":
                "autoscale.api.rackspacecloud.com/v1.0/action/
                db48c04dc6a93f7507b78a0dc37a535fa1f06e1a45ba138d30e3d4b4
                d8addce944e11b6cbc3134af0d203058a40bd239766f97dbcbca5dff
                f1e4df963414dbfe",
            "cooldown": 777
        }


    """
    rec = get_store().get_webhook(tenantId, groupId, policyId, webhookId)
    deferred = defer.maybeDeferred(rec.edit_all_webhooks, data)
    return deferred


@app.route(('/<string:tenantId>/autoscale/<string:groupId>/policy/'
            '<string:policyId>/webhook/<string:webhookId>'),
           methods=['DELETE'])
@fails_with(exception_codes)
@succeeds_with(204)
def delete_webhook(request, tenantId, groupId, policyId, webhookId):
    """
    Delete a scaling policy webhook.
    If successful, no response body will be returned.
    """
    deferred = defer.maybeDeferred(get_store().delete_policy,
                                   tenantId, groupId, policyId, webhookId)
    return deferred
