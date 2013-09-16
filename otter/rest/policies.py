"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/groups/groupId/policies and /tenantId/groups/groupId/policies/policyId)
"""

from functools import partial
import json

from otter.json_schema import rest_schemas, group_schemas
from otter.rest.decorators import (validate_body, fails_with,
                                   succeeds_with, log_arguments,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.otterapp import OtterApp
from otter.rest.webhooks import OtterWebhooks
from otter.util.http import get_autoscale_links, transaction_id
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


class OtterPolicies(object):
    """
    REST endpoints for policies of a scaling group.
    """
    app = OtterApp()

    def __init__(self, store, log, tenant_id, scaling_group_id):
        self.store = store
        self.log = log
        self.tenant_id = tenant_id
        self.scaling_group_id = scaling_group_id

    @app.route('/', methods=['GET'])
    @fails_with(exception_codes)
    @succeeds_with(200)
    def list_policies(self, request):
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
                'policies': policy_dict_to_list(policy_dict, self.tenant_id, self.scaling_group_id),
                "policies_links": []
            }

        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.list_policies()
        deferred.addCallback(format_policies)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/', methods=['POST'])
    @fails_with(exception_codes)
    @succeeds_with(201)
    @validate_body(rest_schemas.create_policies_request)
    def create_policies(self, request, data):
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
                    "name": 'scale down by 5.5 percent',
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
                        "name": 'scale down by 5.5 percent',
                        "changePercent": -5.5,
                        "cooldown": 6
                    }
                ]
            }
        """

        def format_policies_and_send_redirect(policy_dict):
            request.setHeader(
                "Location",
                get_autoscale_links(self.tenant_id, self.scaling_group_id, "", format=None)
            )

            policy_list = []
            for policy_uuid, policy_item in policy_dict.iteritems():
                policy_item['id'] = policy_uuid
                policy_item['links'] = get_autoscale_links(
                    self.tenant_id, self.scaling_group_id, policy_uuid)
                policy_list.append(policy_item)

            return {'policies': policy_list}

        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.create_policies(data)
        deferred.addCallback(format_policies_and_send_redirect)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/<string:policy_id>/', branch=True)
    @with_transaction_id()
    def policy(self, request, log, policy_id):
        """
        Delegate routes for specific policies to OtterPolicy.
        """
        return OtterPolicy(self.store, log, self.tenant_id,
                           self.scaling_group_id,
                           policy_id).app.resource()


class OtterPolicy(object):
    """
    REST endpoints for a specific policy of a scaling group.
    """
    app = OtterApp()

    def __init__(self, store, log, tenant_id, scaling_group_id, policy_id):
        self.store = store
        self.log = log
        self.tenant_id = tenant_id
        self.scaling_group_id = scaling_group_id
        self.policy_id = policy_id

    @app.route('/', methods=['GET'])
    @fails_with(exception_codes)
    @succeeds_with(200)
    @log_arguments
    def get_policy(self, request):
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
            policy_dict['id'] = self.policy_id
            policy_dict['links'] = get_autoscale_links(self.tenant_id,
                                                       self.scaling_group_id,
                                                       self.policy_id)
            return {'policy': policy_dict}

        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.get_policy(self.policy_id)
        deferred.addCallback(openstackify)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/', methods=['PUT'])
    @fails_with(exception_codes)
    @succeeds_with(204)
    @validate_body(group_schemas.policy)
    @log_arguments
    def update_policy(self, request, data):
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
        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.update_policy(self.policy_id, data)
        return deferred

    @app.route('/', methods=['DELETE'])
    @fails_with(exception_codes)
    @succeeds_with(204)
    @log_arguments
    def delete_policy(self, request):
        """
        Delete a scaling policy. If successful, no response body will be returned.
        """
        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.delete_policy(self.policy_id)
        return deferred

    @app.route('/execute/', methods=['POST'])
    @fails_with(exception_codes)
    @succeeds_with(202)
    @log_arguments
    def execute_policy(self, request):
        """
        Execute this scaling policy.

        TBD: Response body.

        Example response::

            {}
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        d = group.modify_state(partial(controller.maybe_execute_scaling_policy,
                                       self.log, transaction_id(request),
                                       policy_id=self.policy_id))
        d.addCallback(lambda _: "{}")  # Return value TBD
        return d

    @app.route('/webhooks/', branch=True)
    @with_transaction_id()
    def webhooks(self, request, log):
        """
        webhook routes handled by OtterWebhooks
        """
        return OtterWebhooks(self.store, log, self.tenant_id,
                             self.scaling_group_id, self.policy_id).app.resource()
