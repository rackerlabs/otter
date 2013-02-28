"""
Autoscale REST endpoints having to do with editing/modifying the configuration
or launch configuration for a scaling group.

(/tenantId/groups/groupId/config and /tenantId/groups/groupId/launch)
"""

import json

from otter.json_schema import group_schemas
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.application import app, get_store


# TODO: in the implementation story, the interface get scaling group
#       definition should be changed to remove colo, and the mock store and
#       corresponding tests also changed
@app.route('/<string:tenantId>/groups/<string:groupId>/config',
           methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def view_config_for_scaling_group(request, log, tenantId, groupId):
    """
    Get the configuration for a scaling group, which includes the minimum
    number of entities, the maximum number of entities, global cooldown, and
    other metadata.  This data is returned in the body of the response in JSON
    format.

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
            }
        }
    """
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.view_config()
    deferred.addCallback(lambda conf: json.dumps({"groupConfiguration": conf}))
    return deferred


# TODO: in the implementation story, the interface get scaling group
#       definition should be changed to remove colo, and the mock store and
#       corresponding tests also changed
@app.route('/<string:tenantId>/groups/<string:groupId>/config',
           methods=['PUT'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(group_schemas.config)
def edit_config_for_scaling_group(request, log, tenantId, groupId, data):
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
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.update_config(data)
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/launch',
           methods=['GET'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(200)
def view_launch_config(request, log, tenantId, groupId):
    """
    Get the launch configuration for a scaling group, which includes the
    details of how to create a server, from what image, which load balancers to
    join it to, and what networks to add it to, and other metadata.
    This data is returned in the body of the response in JSON format.

    Example response::

        {
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
            }
        }
    """
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.view_launch_config()
    deferred.addCallback(lambda conf: json.dumps({"launchConfiguration": conf}))
    return deferred


@app.route('/<string:tenantId>/groups/<string:groupId>/launch',
           methods=['PUT'])
@with_transaction_id()
@fails_with(exception_codes)
@succeeds_with(204)
@validate_body(group_schemas.launch_config)
def edit_launch_config(request, log, tenantId, groupId, data):
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
        }

    The exact update cases are still up in the air -- can the user provide
    a mimimal schema, and if so, what happens with defaults?

    Nova should validate the image before saving the new config.
    Users may have an invalid configuration based on dependencies.
    """
    rec = get_store().get_scaling_group(log, tenantId, groupId)
    deferred = rec.update_launch_config(data)
    return deferred
