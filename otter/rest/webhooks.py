"""
Autoscale REST endpoints having to do with creating/reading/updating/deleting
the webhooks associated with a particular scaling group's particular scaling
policy.

(/tenantId/groups/groupId/policy/policyId/webhook
 /tenantId/groups/groupId/policy/policyId/webhook/webhookId)
"""
from functools import partial
import json

from klein import Klein

from otter.json_schema import group_schemas
from otter.json_schema import rest_schemas
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.util.http import get_autoscale_links, transaction_id

from otter.models.interface import (
    UnrecognizedCapabilityError,
    NoSuchPolicyError,
    NoSuchScalingGroupError
)

from otter.controller import CannotExecutePolicyError
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


class OtterWebhooks(object):
    """
    REST endpoints for managing scaling group webhooks.
    """
    app = Klein()

    def __init__(self, store, tenant_id, group_id, policy_id):
        self.store = store
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.policy_id = policy_id
        self.app.route = partial(self.app.route, strict_slashes=False)

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def list_webhooks(self, request, log):
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
                    _format_webhook(webhook_id, webhook_model, self.tenant_id,
                                    self.group_id, self.policy_id))

            return {
                'webhooks': webhook_list,
                "webhooks_links": []
            }

        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.list_webhooks(self.policy_id)
        deferred.addCallback(format_webhooks)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(201)
    @validate_body(rest_schemas.create_webhooks_request)
    def create_webhooks(self, request, log, data):
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
                get_autoscale_links(self.tenant_id, self.group_id, self.policy_id, "", format=None)
            )

            webhook_list = []
            for webhook_id, webhook_model in webhook_dict.iteritems():
                webhook_list.append(
                    _format_webhook(webhook_id, webhook_model, self.tenant_id,
                                    self.group_id, self.policy_id))

            return {'webhooks': webhook_list}

        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.create_webhooks(self.policy_id, data)
        deferred.addCallback(format_webhooks_and_send_redirect)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/<string:webhook_id>/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def get_webhook(self, request, log, webhook_id):
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
            result = _format_webhook(webhook_id, webhook_model,
                                     self.tenant_id, self.group_id,
                                     self.policy_id)
            return {'webhook': result}

        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.get_webhook(self.policy_id, webhook_id)
        deferred.addCallback(format_one_webhook)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/<string:webhook_id>/', methods=['PUT'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    @validate_body(group_schemas.update_webhook)
    def update_webhook(self, request, log, webhook_id, data):
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
        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.update_webhook(self.policy_id, webhook_id, data)
        return deferred

    @app.route('/<string:webhook_id>/', methods=['DELETE'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def delete_webhook(self, request, log, webhook_id):
        """
        Deletes a particular webhook.
        If successful, no response body will be returned.
        """
        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.delete_webhook(self.policy_id, webhook_id)
        return deferred


class OtterExecute(object):
    """
    REST endpoint for executing a webhook.
    """
    app = Klein()

    def __init__(self, store, capability_version, capability_hash):
        self.store = store
        self.capability_version = capability_version
        self.capability_hash = capability_hash
        self.app.route = partial(self.app.route, strict_slashes=False)

    @app.route('/', methods=['POST'])
    @with_transaction_id()
    @fails_with({})  # This will allow us to surface internal server error only.
    @succeeds_with(202)
    def execute_webhook(self, request, log):
        """
        Execute a scaling policy based the capability hash.
        This returns a 202 in all cases except internal server error,
        and does not wait for execution to finish.
        """
        cap_log = log.bind(capability_hash=self.capability_hash,
                           capability_version=self.capability_version)

        d = self.store.webhook_info_by_hash(log, self.capability_hash)

        def log_informational_webhook_failure(failure):
            failure.trap(UnrecognizedCapabilityError,
                         CannotExecutePolicyError,
                         NoSuchPolicyError,
                         NoSuchScalingGroupError)
            cap_log.msg("Non-fatal error during webhook execution: {exc!r}",
                        exc=failure.value)

        def execute_policy((tenant_id, group_id, policy_id)):
            group = self.store.get_scaling_group(log, tenant_id, group_id)
            return group.modify_state(partial(controller.maybe_execute_scaling_policy,
                                              cap_log, transaction_id(request),
                                              policy_id=policy_id))

        d.addCallback(execute_policy)
        d.addErrback(log_informational_webhook_failure)
        d.addErrback(lambda f: cap_log.err(f, "Unhandled exception executing webhook."))
