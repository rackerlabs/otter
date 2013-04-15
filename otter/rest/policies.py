"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/groups/groupId/policies and /tenantId/groups/groupId/policies/policyId)
"""

import json

from otter.json_schema import rest_schemas, group_schemas
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.application import (app, get_store, get_autoscale_links, transaction_id)
from otter import controller


def policy_dict_to_list(policy_dict, tenantId, groupId):
    """
    Takes dictionary of policies mapping policy ids to the policy blobs, and
    transforms them into a list of dictionaries that contain the keys 'id' and
    'links'.
    """
    policy_list = []
    for policy_uuid, policy_item in policy_dict.iteritems():
        policy_item['id'] = policy_uuid
        policy_item['links'] = get_autoscale_links(
            tenantId, groupId, policy_uuid)
        policy_list.append(policy_item)
    return policy_list


@app.route('/<string:tenantId>/groups/<string:groupId>/policies/',
           methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def list_policies(request, log, tenantId, groupId):
    """
    Get a list of scaling policies in the group. Each policy describes an id,
    name, type, adjustment, cooldown, and links. This data is returned in the
    body of the response in JSON format.

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
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId1}/"
                            "rel": "self"
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
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId2}/"
                            "rel": "self"
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
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId3}/"
                            "rel": "self"
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
                            "href": "{url_root}/v1.0/010101/groups/{groupId1}/policy/{policyId4}/"
                            "rel": "self"
                        }
                    ]
                }
            ]
        }
    """
    def format_policies(policy_dict):
        return {
            'policies': policy_dict_to_list(policy_dict, tenantId, groupId),
            "policies_links": []
        }

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.list_policies()
    deferred.addCallback(format_policies)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/policies/',
           methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(rest_schemas.create_policies_request)
def create_policies(request, log, tenantId, groupId, data):
    """
    Create one or many new scaling policies.
    Scaling policies must include a name, type, adjustment, and cooldown.
    The response header will point to the list policies endpoint.
    An array of scaling policies is provided in the request body in JSON format.

    Example request::

        [
            {
                "name": "scale up by one server",
                "change": 1,
                "cooldown": 150
            },
            {
                "name": 'scale down 5.5 percent',
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
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId1}/"
                            "rel": "self"
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
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId2}/"
                            "rel": "self"
                        }
                    ],
                    "name": 'scale down 5.5 percent',
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

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.create_policies(data)
    deferred.addCallback(format_policies_and_send_redirect)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/',
    methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def get_policy(request, log, tenantId, groupId, policyId):
    """
    Get a scaling policy which describes an id, name, type, adjustment, and
    cooldown, and links.  This data is returned in the body of the response in
    JSON format.

    Example response::

        {
            "policy": {
                "id": {policyId},
                "links": [
                    {
                        "href": "{url_root}/v1.0/010101/groups/{groupId}/policy/{policyId}/"
                        "rel": "self"
                    }
                ],
                "name": "scale up by one server",
                "change": 1,
                "cooldown": 150
            }
        }
    """
    def openstackify(policy_dict):
        policy_dict['id'] = policyId
        policy_dict['links'] = get_autoscale_links(tenantId, groupId, policyId)
        return {'policy': policy_dict}

    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.get_policy(policyId)
    deferred.addCallback(openstackify)
    deferred.addCallback(json.dumps)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/',
    methods=['PUT'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(group_schemas.policy)
def update_policy(request, log, tenantId, groupId, policyId, data):
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
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.update_policy(policyId, data)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/',
    methods=['DELETE'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def delete_policy(request, log, tenantId, groupId, policyId):
    """
    Delete a scaling policy. If successful, no response body will be returned.
    """
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.delete_policy(policyId)
    return deferred


@app.route(
    '/<string:tenantId>/groups/<string:groupId>/policies/<string:policyId>/execute/',
    methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(202)
def execute_policy(request, log, tenantId, groupId, policyId):
    """
    Execute this scaling policy.

    TBD: Response body.

    Example response::

        {}
    """
    group = get_store().get_scaling_group(log, tenantId, groupId)

    d = controller.maybe_execute_scaling_policy(
        log, transaction_id(request), group, policyId)

    d.addCallback(lambda _: "{}")  # Return value TBD
    return d
