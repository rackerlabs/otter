"""
Autoscale REST endpoints having to do with editing/modifying the configuration
or launch configuration for a scaling group.

(/tenantId/groups/groupId/config and /tenantId/groups/groupId/launch)
"""
from functools import partial
import json

from otter.json_schema import group_schemas
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id)
from otter.rest.errors import exception_codes
from otter.rest.otterapp import OtterApp
from otter.util.http import transaction_id

from otter import controller
from otter.rest.errors import InvalidMinEntities


class OtterConfig(object):
    """
    REST endpoints for the configuration of scaling groups.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, group_id):
        self.store = store
        self.tenant_id = tenant_id
        self.group_id = group_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def view_config_for_scaling_group(self, request, log):
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
        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.view_config()
        deferred.addCallback(lambda conf: json.dumps({"groupConfiguration": conf}))
        return deferred

    @app.route('/', methods=['PUT'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    @validate_body(group_schemas.update_config)
    def edit_config_for_scaling_group(self, request, log, data):
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

        The entire schema body must be provided.
        """
        if data['minEntities'] > data['maxEntities']:
            raise InvalidMinEntities("minEntities must be less than or equal to maxEntities")

        def _do_obey_config_change(_, group):
            return group.modify_state(
                partial(controller.obey_config_change, log, transaction_id(request),
                        data))

        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.update_config(data).addCallback(_do_obey_config_change, rec)
        return deferred


class OtterLaunch(object):
    """
    REST endpoints for launch configurations.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, group_id):
        self.store = store
        self.tenant_id = tenant_id
        self.group_id = group_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def view_launch_config(self, request, log):
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
        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.view_launch_config()
        deferred.addCallback(lambda conf: json.dumps({"launchConfiguration": conf}))
        return deferred

    @app.route('/', methods=['PUT'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    @validate_body(group_schemas.launch_config)
    def edit_launch_config(self, request, log, data):
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
        rec = self.store.get_scaling_group(log, self.tenant_id, self.group_id)
        deferred = rec.update_launch_config(data)
        return deferred
