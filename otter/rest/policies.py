"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/groups/groupId/policy and /tenantId/groups/groupId/policy/policyId)
"""

import json

from otter.json_schema import scaling_group as sg_schema
from otter.rest.decorators import validate_body, fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_autoscale_links


@app.route('/<string:tenantId>/groups/<string:groupId>/policy',
           methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def list_policies(request, tenantId, groupId):
    """
    Get a mapping of scaling policy IDs to scaling policies in the group.
    Each policy describes an id, name, type, adjustment, and cooldown.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
            "policies": [
                {
                    "id":"ab2b2865-2e9d-4422-a6aa-5af184f81d7b",
                    "data": {
                        "name": "scale up by one server",
                        "change": 1,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id": "a64b4aa8-03f5-4c46-9bc0-add7c3795809",
                    "data": {
                        "name": "scale up ten percent",
                        "changePercent": 10,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id":"30faf2d1-39db-4c85-9505-07cbe7ab5569",
                    "data": {
                        "name": "scale down one server",
                        "change": -1,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id": "dde7c707-750d-4df5-9828-687bb77cb8fd",
                    "data": {
                        "name": "scale down ten percent",
                        "changePercent": -10,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ]
                }
            ]
        }
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.list_policies()
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/policy',
           methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(sg_schema.create_policy_array)
def create_policy(request, tenantId, groupId, data):
    """
    Create one or many new scaling policies.
    Scaling policies must include a name, type, adjustment, and cooldown.
    The response header will point to the newly created policy.
    This data provided in the request body in JSON format.

    Example request::

        [{
            "name": "scale up by one server",
            "change": 1,
            "cooldown": 150
        }]

    """

    def send_redirect(policyId):
        request.setHeader(
            "Location",
            get_autoscale_links(
                tenantId,
                groupId,
                policyId,
                format=None
            )
        )

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.create_policy(data)
    deferred.addCallback(send_redirect)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policy/<string:policyId>',
    methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def get_policy(request, tenantId, groupId, policyId):
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
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.get_policy(policyId)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policy/<string:policyId>',
    methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(sg_schema.policy)
def update_policy(request, tenantId, groupId, policyId, data):
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
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.update_policy(policyId, data)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policy/<string:policyId>',
    methods=['DELETE'])
@fails_with(exception_codes)
@succeeds_with(204)
def delete_policy(request, tenantId, groupId, policyId):
    """
    Delete a scaling policy. If successful, no response body will be returned.
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.delete_policy(policyId)
    return deferred
