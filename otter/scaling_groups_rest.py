""" Scaling groups REST mock API"""

from klein import resource, route
import json
from jsonschema import ValidationError

from twisted.internet import defer
from twisted.web.resource import Resource

from otter.models.interface import NoSuchScalingGroupError
from otter.json_schema.scaling_group import config as config_schema
from otter.json_schema.scaling_group import (
    launch_server_config_examples as launch_schema
)

from otter.util.schema import InvalidJsonError, validate_body
from otter.util.fault import fails_with, succeeds_with


_store = None
_urlRoot = 'http://127.0.0.1/v1.0'

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


def _format_groups(groups):
    res = {}
    for colo in groups:
        res[colo] = map(lambda format: {'id': format.uuid,
                                        'region': format.region}, groups[colo])
    return res


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
    deferred = defer.maybeDeferred(get_store().list_autoscale, tenantId)
    deferred.addCallback(_format_groups)
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
@validate_body(config_schema)
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
        request.setHeader("Location",
                          "{0}/{1}/autoscale/{3}/".
                          format(get_url_root(), tenantId, uuid))

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
            "scalingStatus": "running"
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
@validate_body(config_schema)
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


@route(('/<string:tenantId>/autoscale/<string:groupId>/launch_config'),
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


@route(('/<string:tenantId>/autoscale/<string:groupId>/launch_config'),
       methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(launch_schema)
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


root = Resource()
root.putChild('v1.0', resource())
