""" Scaling groups REST mock API"""

from klein import resource, route
import json
from jsonschema import ValidationError

from twisted.internet import defer
from twisted.web.resource import Resource

from otter.models.interface import NoSuchScalingGroupError
from otter.json_schema import scaling_group as sg_schema
from otter.util.schema import InvalidJsonError, validate_body
from otter.util.fault import fails_with, succeeds_with


_store = None
_urlRoot = 'http://127.0.0.1'

exception_codes = {
    ValidationError: 400,
    InvalidJsonError: 400,
    NoSuchScalingGroupError: 404
}


def get_store():
    """
    :return: the inventory to be used in forming the REST responses
    :rtype: :class:`cupboard.interface.IInventory` provider
    """
    global _store
    if _store is None:
        from otter.models.mock import MockScalingGroupCollection
        _store = MockScalingGroupCollection()
    return _store


def get_url_root():
    """
    Get the URL root
    :return: string containing the URL root
    """
    global _urlRoot
    return _urlRoot


def set_store(i_store_provider):
    """
    Sets the inventory to use in forming the REST responses

    :param i_inventory_provider: the inventory to be used in forming the REST
        responses
    :type i_inventory_provider: :class:`cupboard.interface.IInventory` provider

    :return: None
    """
    global _store
    _store = i_store_provider


def _get_autoscale_link(tenant_id, group_id=None):
    """
    Generates a link into the autoscale system, based on the ids given.
    """
    link = "{0}/{1!s}/autoscale".format(get_url_root(), tenant_id)
    if group_id is not None:
        link = "{0}/{1!s}".format(link, group_id)
    return link


# -------------------- list scaling groups for tenant id ----------------------

@route('/<string:tenantId>/autoscale',  methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def list_all_scaling_groups(request, tenantId):
    """
    Lists all the autoscaling groups per for a given tenant ID.

    Example response::

        [
            {
                "id": "{instance_id}"
                "link": "https://dfw.autoscale.api.rackspace.com/v1.0/036213/autoscale/{instance_id}"
            },
            {
                "id": "{instance_id}"
                "link": "https://dfw.autoscale.api.rackspace.com/v1.0/036213/autoscale/{instance_id}"
            }
        ]
    """
    def format_list(groups):
        # if this list of groups is ever too large, or getting the link
        # becomes a more time consuming task, perhaps this map should be done
        # cooperatively
        return [
            {
                'id': group.uuid,
                'link': _get_autoscale_link(tenantId, group.uuid)
            } for group in groups]

    deferred = defer.maybeDeferred(get_store().list_scaling_groups, tenantId)
    deferred.addCallback(format_list)
    deferred.addCallback(json.dumps)
    return deferred


# --------------------------- CRD a scaling group -----------------------------
# (CRD = CRUD - U, because updating happens at suburls - so you can update
# different parts)

# TODO: in the implementation ticket, the interface create definition should be
#       changed, and the mock store and corresponding tests also changed.
# C

@route('/<string:tenantId>/autoscale', methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(sg_schema.create_group)
def create_new_scaling_group(request, tenantId, data):
    """
    Create a new scaling group, given the general scaling group configuration,
    launch configuration, and optional scaling policies.  This data provided
    in the request body in JSON format. If successful, no response body will
    be returned.

    Example request body containing some scaling policies::

        {
            "groupConfiguration": {
                "name": "workers",
                "cooldown": 60,
                "minEntities": 5,
                "maxEntities": 100,
                "metadata": {
                    "firstkey": "this is a string",
                    "secondkey": "1"
                }
            },
            "launchConfiguration": {
                "type": "launch_server",
                "args": {
                    "server": {
                        "flavorRef": 3,
                        "name": "webhead",
                        "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                        "OS-DCF:diskConfig": "AUTO",
                        "metadata": {
                            "mykey": "myvalue"
                        },
                        "personality": [
                            {
                                "path": '/root/.ssh/authorized_keys',
                                "contents": (
                                    "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp")
                            }
                        ],
                        "networks": [
                            {
                                "uuid": "11111111-1111-1111-1111-111111111111"
                            }
                        ],
                    },
                    "loadBalancers": [
                        {
                            "loadBalancerId": 2200,
                            "port": 8081
                        }
                    ]
                }
            },
            "scalingPolicies": [
                {
                    "name": "scale up by 10",
                    "change": 10,
                    "cooldown": 5
                }
                {
                    "name": 'scale down 5.5 percent',
                    "changePercent": -5.5,
                    "cooldown": 6
                },
                {
                    "name": 'set number of servers to 10',
                    "steadyState": 10,
                    "cooldown": 3
                }
            ]
        }

    The ``scalingPolicies`` attribute can also be an empty list, or just left
    out entirely.
    """
    def send_redirect(uuid):
        request.setHeader("Location", _get_autoscale_link(tenantId, uuid))

    deferred = defer.maybeDeferred(
        get_store().create_scaling_group, tenantId, data)
    deferred.addCallback(send_redirect)
    return deferred


# TODO: in the implementation story, the interface create definition should be
#       changed to remove colo, and the mock store and corresponding tests
#       also changed
# R
@route('/<string:tenantId>/autoscale/<string:groupId>', methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_manifest_config_for_scaling_group(request, tenantId, groupId):
    """
    View manifested view of the scaling group configuration, including the
    launch configuration, and the scaling policies.  This data is returned in
    the body of the response in JSON format.

    Example response::

        {
            "groupConfiguration": {
                "name": "workers",
                "cooldown": 60,
                "minEntities": 5,
                "maxEntities": 100,
                "metadata": {
                    "firstkey": "this is a string",
                    "secondkey": "1",
                }
            },
            "launchConfiguration": {
                "type": "launch_server",
                "args": {
                    "server": {
                        "flavorRef": 3,
                        "name": "webhead",
                        "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                        "OS-DCF:diskConfig": "AUTO",
                        "metadata": {
                            "mykey": "myvalue"
                        },
                        "personality": [
                            {
                                "path": '/root/.ssh/authorized_keys',
                                "contents": (
                                    "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp")
                            }
                        ],
                        "networks": [
                            {
                                "uuid": "11111111-1111-1111-1111-111111111111"
                            }
                        ],
                    },
                    "loadBalancers": [
                        {
                            "loadBalancerId": 2200,
                            "port": 8081
                        }
                    ]
                }
            },
            "scalingPolicies": [
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
            ]
        }
    """
    raise NotImplementedError()


# TODO: in the implementation story, the interface delete definition should be
#       changed, and the mock store and corresponding tests also changed to
#       not delete if there are existing servers.
# Feature: Force delete, which stops scaling, deletes all servers for you, then
#       deletes the scaling group.
# D
@route('/<string:tenantId>/autoscale/<string:groupId>', methods=['DELETE'])
@fails_with(exception_codes)
@succeeds_with(204)
def delete_scaling_group(request, tenantId, groupId):
    """
    Delete a scaling group if there are no entities belonging to the scaling
    group.  If successful, no response body will be returned.
    """
    deferred = defer.maybeDeferred(get_store().delete_scaling_group,
                                   tenantId, groupId)
    return deferred


@route('/<string:tenantId>/autoscale/<string:groupId>/state', methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def get_scaling_group_state(request, tenantId, coloId, groupId):
    """
    Get the current state of the scaling group, including the current set of
    active entities, the current set of pending entities, the desired number
    of entities, the current desired number of steady state servers.  This
    data is returned in the body of the response in JSON format.

    Example response::

        {
            "active": [
                {
                    "id": "{instance_id}",
                    "link": "https://dfw.servers.api.rackspacecloud.com/v2/203515/servers/{instance_id}"
                },
                {
                    "id": "{instance_id}",
                    "link": "https://dfw.servers.api.rackspacecloud.com/v2/203515/servers/{instance_id}"
                }
            ],
            "pending": [
                {
                    "id": "{instance_id}",
                    "link": "https://dfw.servers.api.rackspacecloud.com/v2/203515/servers/{instance_id}"
                }
            ],
            "steadyState": 3,
            "paused": false
        }
    """
    raise NotImplementedError()


# -------------------- read/update scaling group configs ---------------------

# TODO: in the implementation story, the interface get scaling group
#       definition should be changed to remove colo, and the mock store and
#       corresponding tests also changed
@route('/<string:tenantId>/autoscale/<string:groupId>/config',
       methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_config_for_scaling_group(request, tenantId, groupId):
    """
    Get the configuration for a scaling group, which includes the minimum
    number of entities, the maximum number of entities, global cooldown, and
    other metadata.  This data is returned in the body of the response in JSON
    format.

    Example response::

        {
            "name": "workers",
            "cooldown": 60,
            "minEntities": 5,
            "maxEntities": 100,
            "metadata": {
                "firstkey": "this is a string",
                "secondkey": "1",
            }
        }
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.view_config)
    deferred.addCallback(json.dumps)
    return deferred


# TODO: in the implementation story, the interface get scaling group
#       definition should be changed to remove colo, and the mock store and
#       corresponding tests also changed
@route(('/<string:tenantId>/autoscale/<string:groupId>/config'),
       methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(sg_schema.config)
def edit_config_for_scaling_group(request, tenantId, groupId, data):
    """
    Edit the configuration for a scaling group, which includes the minimum
    number of entities, the maximum number of entities, global cooldown, and
    other metadata.  This data provided in the request body in JSON format.
    If successful, no response body will be returned.

    Example request::

        {
            "name": "workers",
            "cooldown": 60,
            "minEntities": 5,
            "maxEntities": 100,
            "metadata": {
                "firstkey": "this is a string",
                "secondkey": "1",
            }
        }

    The exact update cases are still up in the air -- can the user provide
    a mimimal schema, and if so, what happens with defaults?
    """
    rec = get_store().get_scaling_group(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.update_config, data)
    return deferred


# -------------------- read/update launch configs ---------------------


@route(('/<string:tenantId>/autoscale/<string:groupId>/launch'),
       methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_launch_config(request, tenantId, groupId):
    """
    Get the launch configuration for a scaling group, which includes the
    details of how to create a server, from what image, which load balancers to
    join it to, and what networks to add it to, and other metadata.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": 3,
                    "name": "webhead",
                    "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                    "OS-DCF:diskConfig": "AUTO",
                    "metadata": {
                        "mykey": "myvalue"
                    },
                    "personality": [
                        {
                            "path": '/root/.ssh/authorized_keys',
                            "contents": (
                                "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp")
                        }
                    ],
                    "networks": [
                        {
                            "uuid": "11111111-1111-1111-1111-111111111111"
                        }
                    ],
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": 2200,
                        "port": 8081
                    }
                ]
            }
        }
    """
    rec = get_store().get_launch_config(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.view_config)
    deferred.addCallback(json.dumps)
    return deferred


@route(('/<string:tenantId>/autoscale/<string:groupId>/launch'),
       methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(sg_schema.launch_config)
def edit_launch_config(request, tenantId, groupId, data):
    """
    Edit the launch configuration for a scaling group, which includes the
    details of how to create a server, from what image, which load balancers to
    join it to, and what networks to add it to, and other metadata.
    This data provided in the request body in JSON format.
    If successful, no response body will be returned.

    Example request::

        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": 3,
                    "name": "webhead",
                    "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                    "OS-DCF:diskConfig": "AUTO",
                    "metadata": {
                        "mykey": "myvalue"
                    },
                    "personality": [
                        {
                            "path": '/root/.ssh/authorized_keys',
                            "contents": (
                                "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp")
                        }
                    ],
                    "networks": [
                        {
                            "uuid": "11111111-1111-1111-1111-111111111111"
                        }
                    ],
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": 2200,
                        "port": 8081
                    }
                ]
            }
        }

    The exact update cases are still up in the air -- can the user provide
    a mimimal schema, and if so, what happens with defaults?

    Nova should validate the image before saving the new config.
    Users may have an invalid configuration based on dependencies.
    """
    rec = get_store().get_launch_config(tenantId, groupId)
    deferred = defer.maybeDeferred(rec.update_launch_config, data)
    return deferred


# -------------------- list/create scaling policies ---------------------


@route(('/<string:tenantId>/autoscale/<string:groupId>/policy'),
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


@route(('/<string:tenantId>/autoscale/<string:groupId>/policy'),
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

# -------------------- view/edit/delete scaling policies ---------------------


@route(('/<string:tenantId>/autoscale/<string:groupId>'
        '/policy/<string:policyId>'), methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def view_policy(request, tenantId, groupId, policyId):
    """
    Get a scaling policy which describes a name, type, adjustment, and cooldown.
    This data is returned in the body of the response in JSON format.

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


@route(('/<string:tenantId>/autoscale/<string:groupId>'
        '/policy/<string:policyId>'), methods=['PUT'])
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


@route('/<string:tenantId>/autoscale/<string:groupId>/policy/<string:policyId>',
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


# -------------------- view/create/update scaling webhooks ---------------------


@route(('/<string:tenantId>/autoscale/<string:groupId>'
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


@route(('/<string:tenantId>/autoscale/<string:groupId>'
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


@route(('/<string:tenantId>/autoscale/<string:groupId>'
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


@route(('/<string:tenantId>/autoscale/<string:groupId>'
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


@route(('/<string:tenantId>/autoscale/<string:groupId>/policy/'
        '<string:policyId>/webhook/<string:webhookId>'), methods=['DELETE'])
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


root = Resource()
root.putChild('v1.0', resource())
