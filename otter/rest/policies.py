"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/autoscale/groupId/policy and
/tenantId/autoscale/groupId/policy/policyId)
"""

import json

from twisted.internet import defer

from otter.json_schema import scaling_group as sg_schema
from otter.rest.decorators import validate_body, fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_url_root


@app.route('/<string:tenantId>/autoscale/<string:groupId>/policy',
           methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def get_policies(request, tenantId, groupId):
    """
    Get a mapping of scaling policy IDs to scaling policies in the group.
    Each policy describes an id, name, type, adjustment, and cooldown.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
            "ab2b2865-2e9d-4422-a6aa-5af184f81d7b": {
                "name": "scale up by one server",
                "change": 1,
                "cooldown": 150
            },
            "a64b4aa8-03f5-4c46-9bc0-add7c3795809": {
                "name": "scale up ten percent",
                "changePercent": 10,
                "cooldown": 150
            },
            "30faf2d1-39db-4c85-9505-07cbe7ab5569": {
                "name": "scale down one server",
                "change": -1,
                "cooldown": 150
            },
            "dde7c707-750d-4df5-9828-687bb77cb8fd": {
                "name": "scale down ten percent",
                "changePercent": -10,
                "cooldown": 150
            }
        }
    """
    rec = get_store().get_policies(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.view_policies)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/autoscale/<string:groupId>/policy',
           methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(sg_schema.policy)
def create_policy(request, tenantId, groupId, data):
    """
    Create a new scaling policy. Scaling policies must include a name, type,
    adjustment, and cooldown.
    The response header will point to the newly created policy.
    This data provided in the request body in JSON format.

    Example request::

        {
            "name": "scale up by one server",
            "change": 1,
            "cooldown": 150
        }

    """

    def send_redirect(groupId, policyId):
        request.setHeader(
            "Location",
            "{0}/{1}/autoscale/{2}/policy/{3}".format(
                get_url_root(),
                tenantId,
                groupId,
                policyId
            )
        )

    rec = get_store().get_policy(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.create_policy, data)
    deferred.addCallback(send_redirect)
    return deferred


@app.route(
    '/<string:tenantId>/autoscale/<string:groupId>/policy/<string:policyId>',
    methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_policy(request, tenantId, groupId, policyId):
    """
    Get a scaling policy which describes a name, type, adjustment, and
    cooldown. This data is returned in the body of the response in JSON format.

    Example response::

        {
            "name": "scale up by one server",
            "change": 1,
            "cooldown": 150
        }
    """
    rec = get_store().get_policy(tenantId, groupId, policyId)
    deferred = defer.maybeDeferred(rec.view_policy)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/autoscale/<string:groupId>/policy/<string:policyId>',
    methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(sg_schema.policy)
def edit_policy(request, tenantId, groupId, policyId, data):
    """
    Updates a scaling policy. Scaling policies must include a name, type,
    adjustment, and cooldown.
    If successful, no response body will be returned.

    Example request::

        {
            "name": "scale up by two servers",
            "change": 2,
            "cooldown": 150
        }


    """
    rec = get_store().get_policy(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.edit_policy, data)
    return deferred


@app.route(
    '/<string:tenantId>/autoscale/<string:groupId>/policy/<string:policyId>',
    methods=['DELETE'])
@fails_with(exception_codes)
@succeeds_with(204)
def delete_policy(request, tenantId, groupId, policyId):
    """
    Delete a scaling policy. If successful, no response body will be returned.
    """
    deferred = defer.maybeDeferred(get_store().delete_policy,
                                   tenantId, groupId, policyId)
    return deferred
