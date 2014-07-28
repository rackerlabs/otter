"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the scaling policies associated with a particular scaling group.

(/tenantId/groups/groupId/policies and /tenantId/groups/groupId/policies/policyId)
"""

from functools import partial
import json
from twisted.internet import defer

from otter.json_schema import rest_schemas, group_schemas
from otter.log import log
from otter.rest.decorators import (validate_body, fails_with, auditable,
                                   succeeds_with, with_transaction_id, paginatable)
from otter.rest.errors import exception_codes
from otter.rest.otterapp import OtterApp
from otter.rest.webhooks import OtterWebhooks
from otter.util.http import get_autoscale_links, transaction_id, get_policies_links
from otter import controller
from jsonschema import ValidationError


def linkify_policy_list(policy_list, tenantId, groupId):
    """
    Takes list of policies and adds 'links'.
    """
    for policy in policy_list:
        policy['links'] = get_autoscale_links(tenantId, groupId, policy['id'])


def extra_policy_validation(policy_list, bobby):
    """
    Ensure that cloud_monitoring policies don't look like scheduled policies and
    vice versa
    """
    for policy in policy_list:
        if policy['type'] == 'cloud_monitoring':
            if bobby is None:
                e = ValidationError('cloud_monitoring policy disabled')
                return e
            if 'at' in policy['args'] or 'cron' in policy['args']:
                e = ValidationError('Incorrect args for cloud_monitoring policy')
                return e
        if policy['type'] == 'schedule':
            if 'check' in policy['args'] or 'alarm_criteria' in policy['args']:
                e = ValidationError('Incorrect args for schedule policy')
                return e
    return None


class OtterPolicies(object):
    """
    REST endpoints for policies of a scaling group.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, scaling_group_id):
        self.log = log.bind(system='otter.rest.policies',
                            tenant_id=tenant_id,
                            scaling_group_id=scaling_group_id)
        self.store = store
        self.tenant_id = tenant_id
        self.scaling_group_id = scaling_group_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    @paginatable
    def list_policies(self, request, paginate):
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
        def format_policies(policy_list):
            linkify_policy_list(policy_list, self.tenant_id, self.scaling_group_id)
            return {
                'policies': policy_list,
                "policies_links": get_policies_links(policy_list, self.tenant_id,
                                                     self.scaling_group_id, None, **paginate)
            }

        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.list_policies(**paginate)
        deferred.addCallback(format_policies)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(201)
    @auditable('request.policy.create', 'Created policies.')
    @validate_body(rest_schemas.create_policies_request)
    def create_policies(self, request, data, audit_logger):
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

        def format_policies_and_send_redirect(policy_list):
            request.setHeader(
                "Location",
                get_autoscale_links(self.tenant_id, self.scaling_group_id, "", format=None)
            )
            linkify_policy_list(policy_list, self.tenant_id, self.scaling_group_id)
            return {'policies': policy_list}

        def _add_to_bobby(policy_list, client):
            d = defer.succeed(policy_list)
            for policy_item in policy_list:
                if policy_item['type'] == 'cloud_monitoring':
                    client.create_policy(self.tenant_id, self.scaling_group_id, policy_item['id'],
                                         policy_item['args']['check'],
                                         policy_item['args']['alarm_criteria']['criteria'])
            return d.addCallback(lambda _: policy_list)

        from otter.rest.bobby import get_bobby

        bobby = get_bobby()
        e = extra_policy_validation(data, bobby)
        if e is not None:
            return defer.fail(e)

        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.create_policies(data)

        if bobby is not None:
            deferred.addCallback(_add_to_bobby, bobby)

        deferred.addCallback(format_policies_and_send_redirect)

        def audit_data(result):
            audit_logger.add(data=result)
            return result

        deferred.addCallback(audit_data)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/<string:policy_id>/', branch=True)
    def policy(self, request, policy_id):
        """
        Delegate routes for specific policies to OtterPolicy.
        """
        return OtterPolicy(self.store, self.tenant_id,
                           self.scaling_group_id,
                           policy_id).app.resource()


class OtterPolicy(object):
    """
    REST endpoints for a specific policy of a scaling group.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, scaling_group_id, policy_id):
        self.log = log.bind(system='otter.log.policy',
                            tenant_id=tenant_id,
                            scaling_group_id=scaling_group_id,
                            policy_id=policy_id)
        self.store = store
        self.tenant_id = tenant_id
        self.scaling_group_id = scaling_group_id
        self.policy_id = policy_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
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
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    @validate_body(group_schemas.policy)
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
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    @auditable('request.policy.delete', 'Deleted scaling policy {policy_id}.')
    def delete_policy(self, request, audit_logger):
        """
        Delete a scaling policy. If successful, no response body will be returned.
        """
        rec = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        deferred = rec.delete_policy(self.policy_id)
        return deferred

    @app.route('/execute/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(202)
    def execute_policy(self, request):
        """
        Execute this scaling policy.

        TBD: Response body.

        Example response::

            {}
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id, self.scaling_group_id)
        d = group.modify_desired(partial(controller.maybe_execute_scaling_policy,
                                         self.log, transaction_id(request),
                                         policy_id=self.policy_id))
        d.addCallback(lambda _: "{}")  # Return value TBD
        return d

    @app.route('/webhooks/', branch=True)
    def webhooks(self, request):
        """
        webhook routes handled by OtterWebhooks
        """
        return OtterWebhooks(self.store, self.tenant_id,
                             self.scaling_group_id, self.policy_id).app.resource()
