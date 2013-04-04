"""
Autoscale REST endpoints having to do with a group or collection of groups
(/tenantId/groups and /tenantId/groups/groupId)
"""

import json

from otter.json_schema.rest_schemas import create_group_request
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_autoscale_links, get_store

from otter import controller


@app.route('/<string:tenantId>/groups/',  methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def list_all_scaling_groups(request, log, tenantId):
    """
    Lists all the autoscaling groups per for a given tenant ID.

    Example response::

      {
        "groups": [
          {
            "id": "{groupId1}"
            "links": [
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId1}"
                "rel": "self"
              }
            ]
          },
          {
            "id": "{groupId2}"
            "links": [
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId2}",
                "rel": "self"
              }
            ]
          }
        ],
        "groups_links": []
      }
    """
    def format_list(groups):
        # if this list of groups is ever too large, or getting the link
        # becomes a more time consuming task, perhaps this map should be done
        # cooperatively
        return {
            "groups": [
                {
                    'id': group.uuid,
                    'links': get_autoscale_links(tenantId, group.uuid)
                } for group in groups
            ],
            "groups_links": []
        }

    deferred = get_store().list_scaling_groups(log, tenantId)
    deferred.addCallback(format_list)
    deferred.addCallback(json.dumps)
    return deferred


# --------------------------- CRD a scaling group -----------------------------
# (CRD = CRUD - U, because updating happens at suburls - so you can update
# different parts)

# TODO: Currently, the response does not include scaling policy ids, because
# we are just repeating whatever the request body was, with an ID and links
# attached.  If we are going to create the scaling policies here too, we should
# probably also return their ids and links, just like the manifest.
@app.route('/<string:tenantId>/groups/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(create_group_request)
def create_new_scaling_group(request, log, tenantId, data):
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
                                "contents": "ssh-rsa AAAAB3Nza...LiPk== user@example.net"
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
                },
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

    Example response body to the above request::

        {
            "group": {
                "id": "{groupId}",
                "links": [
                  {
                    "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId}/"
                    "rel": "self"
                  }
                ],
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
                                    "contents": "ssh-rsa AAAAB3Nza...LiPk== user@example.net"
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
        }

    """
    def send_redirect(result, data):
        uuid = result['id']
        request.setHeader(
            "Location", get_autoscale_links(tenantId, uuid, format=None))
        wrapped = {
            "id": uuid,
            "links": get_autoscale_links(tenantId, uuid)
        }
        wrapped.update(data)
        return {"group": wrapped}

    deferred = get_store().create_scaling_group(
        log, tenantId, data['groupConfiguration'], data['launchConfiguration'],
        data.get('scalingPolicies', None))
    deferred.addCallback(send_redirect, data)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/', methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def view_manifest_config_for_scaling_group(request, log, tenantId, groupId):
    """
    View manifested view of the scaling group configuration, including the
    launch configuration, and the scaling policies.  This data is returned in
    the body of the response in JSON format.

    Example response::

        {
            "group": {
                "id": "{groupId}",
                "links": [
                  {
                    "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId}/"
                    "rel": "self"
                  }
                ],
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
                                    "contents": "ssh-rsa AAAAB3Nza...LiPk== user@example.net"
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
                        "id": "{policyId1}",
                        "links": [
                          {
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policies/{policyId1}/"
                            "rel": "self"
                          }
                        ],
                        "name": "scale up by 10",
                        "change": 10,
                        "cooldown": 5
                    }
                    {
                        "id": "{policyId2}",
                        "links": [
                          {
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policies/{policyId2}/"
                            "rel": "self"
                          }
                        ],
                        "name": 'scale down 5.5 percent',
                        "changePercent": -5.5,
                        "cooldown": 6
                    },
                    {
                        "id": "{policyId3}",
                        "links": [
                          {
                            "href": "{url_root}/v1.0/010101/groups/{groupId}/policies/{policyId3}/"
                            "rel": "self"
                          }
                        ],
                        "name": 'set number of servers to 10',
                        "steadyState": 10,
                        "cooldown": 3
                    }
                ]
            }
        }
    """
    def openstack_formatting(data, uuid):
        data["links"] = get_autoscale_links(tenantId, uuid)

        policies = []
        for policy_id, policy in data["scalingPolicies"].iteritems():
            policy["id"] = policy_id
            policy["links"] = get_autoscale_links(tenantId, uuid, policy_id)
            policies.append(policy)

        data["scalingPolicies"] = policies

        return {"group": data}

    group = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = group.view_manifest()
    deferred.addCallback(openstack_formatting, group.uuid)
    deferred.addCallback(json.dumps)
    return deferred


# Feature: Force delete, which stops scaling, deletes all servers for you, then
#       deletes the scaling group.
@app.route('/<string:tenantId>/groups/<string:groupId>/', methods=['DELETE'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def delete_scaling_group(request, log, tenantId, groupId):
    """
    Delete a scaling group if there are no entities belonging to the scaling
    group.  If successful, no response body will be returned.
    """
    return get_store().delete_scaling_group(log, tenantId, groupId)


@app.route('/<string:tenantId>/groups/<string:groupId>/state/',
           methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def get_scaling_group_state(request, log, tenantId, groupId):
    """
    Get the current state of the scaling group, including the current set of
    active entities, the current set of pending entities, the desired number
    of entities, the current desired number of steady state servers.  This
    data is returned in the body of the response in JSON format.

    There is no guarantee about the sort order of the list of active entities.

    Example response::

        {
          "group": {
            "id": "{groupId}",
            "links": [
              {
                "href": "{url_root}/v1.0/010101/groups/{groupId},
                "rel": "self"
              }
            ],
            "active": [
              {
                "id": "{instanceId1}"
                "links": [
                  {
                    "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId1}",
                    "rel": "self"
                  }
                ]
              },
              {
                "id": "{instanceId2}"
                "links": [
                  {
                    "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId2}",
                    "rel": "self"
                  }
                ]
              }
            ],
            "numActive": 2,
            "numPending": 2,
            "steadyState": 4,
            "paused": false
          }
        }
    """
    def reformat_active_and_pending(state_blob):
        response_dict = {
            'numActive': len(state_blob['active']),
            'numPending': len(state_blob['pending']),
            'paused': state_blob['paused']
        }
        response_dict['steadyState'] = (
            response_dict['numActive'] + response_dict['numPending'])

        response_dict['active'] = [
            {
                'id': server_blob['instanceId'],
                'links': [{
                    'href': server_blob['instanceUri'],
                    'rel': 'self'
                }]
            } for key, server_blob in state_blob['active'].iteritems()]

        response_dict["id"] = groupId
        response_dict["links"] = get_autoscale_links(tenantId, groupId)
        return {"group": response_dict}

    group = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = group.view_state()
    deferred.addCallback(reformat_active_and_pending)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/pause/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def pause_scaling_group(request, log, tenantId, groupId):
    """
    Pause a scaling group.  This means that no scaling policies will get
    executed (execution will be rejected).  This is an idempotent operation -
    pausing an already paused group does nothing.
    """
    group = get_store().get_scaling_group(log, tenantId, groupId)
    transaction_id = request.responseHeaders.getRawHeaders('X-Response-Id')[0]
    return controller.pause_scaling_group(log, transaction_id, group)


@app.route('/<string:tenantId>/groups/<string:groupId>/resume/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def resume_scaling_group(request, log, tenantId, groupId):
    """
    Resume a scaling group.  This means that scaling policies will now get
    executed as usual.  This is an idempotent operation - resuming an already
    running group does nothing.
    """
    group = get_store().get_scaling_group(log, tenantId, groupId)
    transaction_id = request.responseHeaders.getRawHeaders('X-Response-Id')[0]
    return controller.resume_scaling_group(log, transaction_id, group)
