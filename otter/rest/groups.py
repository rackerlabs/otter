"""
Autoscale REST endpoints having to do with a group or collection of groups
(/tenantId/autoscale and /tenantId/autoscale/groupId)
"""

import json

from twisted.internet import defer

from otter.json_schema import scaling_group as sg_schema
from otter.rest.decorators import validate_body, fails_with, succeeds_with
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_autoscale_links, get_store


@app.route('/<string:tenantId>/autoscale',  methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def list_all_scaling_groups(request, tenantId):
    """
    Lists all the autoscaling groups per for a given tenant ID.

    Example response::

        [
          {
            "id": "{groupId1}"
            "links": [
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/autoscale/{groupId1}"
                "rel": "self"
              },
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/autoscale/{groupId1}"
                "rel": "bookmark"
              }
            ]
          },
          {
            "id": "{groupId2}"
            "links": [
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/autoscale/{groupId2}",
                "rel": "self"
              },
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/010101/autoscale/{groupId2}"
                "rel": "bookmark"
              }
            ]
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
                'links': get_autoscale_links(tenantId, group.uuid)
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

@app.route('/<string:tenantId>/autoscale', methods=['POST'])
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
        request.setHeader(
            "Location", get_autoscale_links(tenantId, uuid, format=None))

    deferred = defer.maybeDeferred(
        get_store().create_scaling_group, tenantId, data)
    deferred.addCallback(send_redirect)
    return deferred


# TODO: in the implementation story, the interface create definition should be
#       changed to remove colo, and the mock store and corresponding tests
#       also changed
# R
@app.route('/<string:tenantId>/autoscale/<string:groupId>', methods=['GET'])
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
@app.route('/<string:tenantId>/autoscale/<string:groupId>', methods=['DELETE'])
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


@app.route('/<string:tenantId>/autoscale/<string:groupId>/state',
           methods=['GET'])
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
