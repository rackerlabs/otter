"""
Autoscale REST endpoints having to do with a group or collection of groups
(/tenantId/groups and /tenantId/groups/groupId)
"""
from functools import partial
import json

from otter import controller

from otter.json_schema.rest_schemas import create_group_request
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.rest.application import app, get_autoscale_links, get_store, transaction_id
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.policies import policy_dict_to_list
from otter.rest.errors import InvalidMinEntities
from otter.rest.application import get_bobby


def format_state_dict(state):
    """
    Takes a state returned by the model and reformats it to be returned as a
    response.

    :param state: a :class:`otter.models.interface.GroupState` object

    :return: a ``dict`` that looks like what should be respond by the API
        response when getting state
    """
    return {
        'activeCapacity': len(state.active),
        'pendingCapacity': len(state.pending),
        'desiredCapacity': len(state.active) + len(state.pending),
        'paused': state.paused,
        'id': state.group_id,
        'links': get_autoscale_links(state.tenant_id, state.group_id),
        'active': [
            {
                'id': key,
                'links': server_blob['links'],
            } for key, server_blob in state.active.iteritems()
        ]
    }


@app.route('/<string:tenant_id>/groups/',  methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def list_all_scaling_groups(request, log, tenant_id):
    """
    Lists all the autoscaling groups and their states per for a given tenant ID.

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
            ],
            "active": [],
            "activeCapacity": 0,
            "pendingCapacity": 1,
            "desiredCapacity": 1,
            "paused": false
          },
          {
            "id": "{groupId2}"
            "links": [
              {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/010101/groups/{groupId2}",
                "rel": "self"
              }
            ],
            "active": [],
            "activeCapacity": 0,
            "pendingCapacity": 2,
            "desiredCapacity": 2,
            "paused": false
          }
        ],
        "groups_links": []
      }

    TODO:
    """
    def format_list(group_states):
        return {
            "groups": [format_state_dict(state) for state in group_states],
            "groups_links": []
        }

    deferred = get_store().list_scaling_group_states(log, tenant_id)
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
@app.route('/<string:tenant_id>/groups/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(create_group_request)
def create_new_scaling_group(request, log, tenant_id, data):
    """
    Create a new scaling group, given the general scaling group configuration,
    launch configuration, and optional scaling policies.  This data provided
    in the request body in JSON format. If successful, the created group in JSON
    format containing id and links is returned.

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
                    "name": 'scale down by 5.5 percent',
                    "changePercent": -5.5,
                    "cooldown": 6
                },
                {
                    "name": 'set number of servers to 10',
                    "desiredCapacity": 10,
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
                        "name": 'scale down by 5.5 percent',
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
                        "desiredCapacity": 10,
                        "cooldown": 3
                    }
                ]
            }
        }

    """
    data['groupConfiguration'].setdefault('maxEntities', MAX_ENTITIES)
    data['groupConfiguration'].setdefault('metadata', {})

    if data['groupConfiguration']['minEntities'] > data['groupConfiguration']['maxEntities']:
        raise InvalidMinEntities("minEntities must be less than or equal to maxEntities")

    deferred = get_store().create_scaling_group(
        log, tenant_id, data['groupConfiguration'], data['launchConfiguration'],
        data.get('scalingPolicies', None))

    def _do_obey_config_change(result):
        group_id = result['id']
        config = result['groupConfiguration']
        group = get_store().get_scaling_group(log, tenant_id, group_id)
        d = group.modify_state(partial(controller.obey_config_change, log,
                                       transaction_id(request), config))
        return d.addCallback(lambda _: result)

    deferred.addCallback(_do_obey_config_change)

    def _add_to_bobby(result, client):
        d = client.create_group(tenant_id, result["id"])
        return d.addCallback(lambda _: result)

    bobby = get_bobby()
    if bobby is not None:
        deferred.addCallback(_add_to_bobby, bobby)

    def _format_output(result):
        uuid = result['id']
        request.setHeader(
            "Location", get_autoscale_links(tenant_id, uuid, format=None))
        result["links"] = get_autoscale_links(tenant_id, uuid)
        result["scalingPolicies"] = policy_dict_to_list(
            result["scalingPolicies"], tenant_id, uuid)
        return {"group": result}

    deferred.addCallback(_format_output)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenant_id>/groups/<string:scaling_group_id>/', methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def view_manifest_config_for_scaling_group(request, log, tenant_id, scaling_group_id):
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
                        "name": 'scale down by 5.5 percent',
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
                        "desiredCapacity": 10,
                        "cooldown": 3
                    }
                ]
            }
        }
    """
    def openstack_formatting(data, uuid):
        data["links"] = get_autoscale_links(tenant_id, uuid)

        policies = []
        for policy_id, policy in data["scalingPolicies"].iteritems():
            policy["id"] = policy_id
            policy["links"] = get_autoscale_links(tenant_id, uuid, policy_id)
            policies.append(policy)

        data["scalingPolicies"] = policies

        return {"group": data}

    group = get_store().get_scaling_group(log, tenant_id, scaling_group_id)
    deferred = group.view_manifest()
    deferred.addCallback(openstack_formatting, group.uuid)
    deferred.addCallback(json.dumps)
    return deferred


# Feature: Force delete, which stops scaling, deletes all servers for you, then
#       deletes the scaling group.
@app.route('/<string:tenant_id>/groups/<string:scaling_group_id>/', methods=['DELETE'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def delete_scaling_group(request, log, tenant_id, scaling_group_id):
    """
    Delete a scaling group if there are no entities belonging to the scaling
    group.  If successful, no response body will be returned.
    """
    return get_store().get_scaling_group(log, tenant_id, scaling_group_id).delete_group()


@app.route('/<string:tenant_id>/groups/<string:scaling_group_id>/state/',
           methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def get_scaling_group_state(request, log, tenant_id, scaling_group_id):
    """
    Get the current state of the scaling group, including the current set of
    active entities, number of pending entities, and the desired number
    of entities.  This data is returned in the body of the response in JSON format.

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
            "activeCapacity": 2,
            "pendingCapacity": 2,
            "desiredCapacity": 4,
            "paused": false
          }
        }
    """
    def _format_and_stackify(state):
        return {"group": format_state_dict(state)}

    group = get_store().get_scaling_group(log, tenant_id, scaling_group_id)
    deferred = group.view_state()
    deferred.addCallback(_format_and_stackify)
    deferred.addCallback(json.dumps)
    return deferred


@app.route('/<string:tenant_id>/groups/<string:scaling_group_id>/pause/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def pause_scaling_group(request, log, tenant_id, scaling_group_id):
    """
    Pause a scaling group.  This means that no scaling policies will get
    executed (execution will be rejected).  This is an idempotent operation -
    pausing an already paused group does nothing.
    """
    group = get_store().get_scaling_group(log, tenant_id, scaling_group_id)
    return controller.pause_scaling_group(log, transaction_id(request), group)


@app.route('/<string:tenant_id>/groups/<string:scaling_group_id>/resume/', methods=['POST'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
def resume_scaling_group(request, log, tenant_id, scaling_group_id):
    """
    Resume a scaling group.  This means that scaling policies will now get
    executed as usual.  This is an idempotent operation - resuming an already
    running group does nothing.
    """
    group = get_store().get_scaling_group(log, tenant_id, scaling_group_id)
    return controller.resume_scaling_group(log, transaction_id(request), group)
