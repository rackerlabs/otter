"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/groups/groupId/policy and /tenantId/groups/groupId/policy/policyId)
"""

import json

from otter.json_schema import rest_schemas, group_schemas
from otter.rest.decorators import validate_body, fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store, get_autoscale_links


@app.route('/<string:tenantId>/groups/<string:groupId>/policies',
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
                    "id":"{policyId1}",
                    "data": {
                        "name": "scale up by one server",
                        "change": 1,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId1}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id": "{policyId2}",
                    "data": {
                        "name": "scale up ten percent",
                        "changePercent": 10,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId2}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId1}/policy/{policyId2}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id":"{policyId3}",
                    "data": {
                        "name": "scale down one server",
                        "change": -1,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId3}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId1}/policy/{policyId3}"
                            "rel": "bookmark"
                        }
                    ]
                },
                {
                    "id": "{policyId4}",
                    "data": {
                        "name": "scale down ten percent",
                        "changePercent": -10,
                        "cooldown": 150
                    },
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId4}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId1}/policy/{policyId4}"
                            "rel": "bookmark"
                        }
                    ]
                }
            ]
        }
    """
    def format_policies(policy_dict):
        policy_list = []
        for policy_uuid, policy_item in policy_dict.iteritems():
            policy_item['id'] = policy_uuid
            policy_item['links'] = get_autoscale_links(
                tenantId, groupId, policy_uuid)
            policy_list.append(policy_item)

        return {
            'policies': policy_list,
            "policies_links": []
        }

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.list_policies()
    deferred.addCallback(format_policies)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/policies',
           methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(rest_schemas.create_policies_request)
def create_policies(request, tenantId, groupId, data):
    """
    Create one or many new scaling policies.
    Scaling policies must include a name, type, adjustment, and cooldown.
    The response header will point to the list policies endpoint.
    This data provided in the request body in JSON format.

    Example request::

        [
            {
                "name": "scale up by one server",
                "change": 1,
                "cooldown": 150
            },
            {
                "name": 'scale down a 5.5 percent because of a tweet',
                "changePercent": -5.5,
                "cooldown": 6
            }
        ]

    Example response::

        {
            "policies": [
                {
                    "id": {policyId1},
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId1}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId}/policy/{policyId1}"
                            "rel": "bookmark"
                        }
                    ],
                    "name": "scale up by one server",
                    "change": 1,
                    "cooldown": 150
                },
                {
                    "id": {policyId2},
                    "links": [
                        {
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId2}"
                            "rel": "self"
                        },
                        {
                            "href": "{url_root}/010101/groups/{groupId}/policy/{policyId2}"
                            "rel": "bookmark"
                        }
                    ],
                    "name": 'scale down a 5.5 percent because of a tweet',
                    "changePercent": -5.5,
                    "cooldown": 6
                }
            ]
        }
    """

    def format_policies_and_send_redirect(policy_dict):
        request.setHeader(
            "Location",
            get_autoscale_links(tenantId, groupId, "", format=None)
        )

        policy_list = []
        for policy_uuid, policy_item in policy_dict.iteritems():
            policy_item['id'] = policy_uuid
            policy_item['links'] = get_autoscale_links(
                tenantId, groupId, policy_uuid)
            policy_list.append(policy_item)

        return {'policies': policy_list}

    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.create_policies(data)
    deferred.addCallback(format_policies_and_send_redirect)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>',
    methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def get_policy(request, tenantId, groupId, policyId):
    """
    Get a scaling policy which describes a name, type, adjustment, and
    cooldown. This data is returned in the body of the response in JSON format.

    Example response::

        {
            "policy": {
                "id": {policyId},
                "links": [
                    {
                        "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId}"
                        "rel": "self"
                    },
                    {
                        "href": "{url_root}/010101/groups/{groupId}/policy/{policyId}"
                        "rel": "bookmark"
                    }
                ],
                "name": "scale up by one server",
                "change": 1,
                "cooldown": 150
            }
        }
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = rec.get_policy(policyId)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>',
    methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(group_schemas.policy)
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
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>',
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
