"""
Autoscale REST endpoints having to do with a group or collection of groups
(/tenantId/groups and /tenantId/groups/groupId)
"""
from functools import partial
import json

from twisted.internet import defer

from otter import controller
from otter.supervisor import get_supervisor

from otter.json_schema.rest_schemas import create_group_request
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.log import log
from otter.rest.configs import OtterConfig, OtterLaunch
from otter.rest.decorators import (validate_body, fails_with, succeeds_with,
                                   with_transaction_id, paginatable,
                                   InvalidQueryArgument)
from otter.rest.errors import exception_codes
from otter.rest.policies import OtterPolicies, linkify_policy_list
from otter.rest.errors import InvalidMinEntities
from otter.rest.otterapp import OtterApp
from otter.util.http import (get_autoscale_links, transaction_id, get_groups_links,
                             get_policies_links)
from otter.rest.bobby import get_bobby


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
        'name': state.group_name,
        'paused': state.paused,
        'active': [
            {
                'id': key,
                'links': server_blob['links'],
            } for key, server_blob in state.active.iteritems()
        ]
    }


class OtterGroups(object):
    """
    REST endpoints for managing scaling groups.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id):
        self.log = log.bind(system='otter.rest.groups',
                            tenant_id=tenant_id)
        self.store = store
        self.tenant_id = tenant_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    @paginatable
    def list_all_scaling_groups(self, request, paginate):
        """
        Lists all the autoscaling groups and their states per for a given tenant ID.

        Example response::

            {
                "groups": [
                    {
                        "id": "e41380ae-173c-4b40-848a-25c16d7fa83d",
                        "links": [
                            {
                                "href": "https://dfw.autoscale.api.rackspacecloud.com/
                                v1.0/676873/groups/e41380ae-173c-4b40-848a-25c16d7fa83d/",
                                "rel": "self"
                            }
                        ],
                        "state": {
                            "active": [],
                            "activeCapacity": 0,
                            "desiredCapacity": 0,
                            "paused": false,
                            "pendingCapacity": 0,
                            "name": "testscalinggroup198547"
                        }
                    },
                    {
                        "id": "f82bb000-f451-40c8-9dc3-6919097d2f7e",
                        "state": {
                            "active": [],
                            "activeCapacity": 0,
                            "desiredCapacity": 0,
                            "paused": false,
                            "pendingCapacity": 0,
                            "name": "testscalinggroup194547"
                        },
                        "links": [
                            {
                                "href": "https://dfw.autoscale.api.rackspacecloud.com/
                                v1.0/676873/groups/f82bb000-f451-40c8-9dc3-6919097d2f7e/",
                                "rel": "self"
                            }
                        ]
                    }
                ],
                "groups_links": []
            }


        """

        def format_list(group_states):
            groups = [{
                'id': state.group_id,
                'links': get_autoscale_links(state.tenant_id, state.group_id),
                'state': format_state_dict(state)
            } for state in group_states]
            return {
                "groups": groups,
                "groups_links": get_groups_links(groups, self.tenant_id, None, **paginate)
            }

        deferred = self.store.list_scaling_group_states(
            self.log, self.tenant_id, **paginate)
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
    @app.route('/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(201)
    @validate_body(create_group_request)
    def create_new_scaling_group(self, request, data):
        """
        Create a new scaling group, given the general scaling group configuration,
        launch configuration, and optional scaling policies.  This data provided
        in the request body in JSON format. If successful, the created group in JSON
        format containing id and links is returned.

        Example request body containing some scaling policies::

            {
              "launchConfiguration": {
                "args": {
                  "loadBalancers": [
                    {
                      "port": 8080,
                      "loadBalancerId": 9099
                    }
                  ],
                  "server": {
                    "name": "autoscale_server",
                    "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                    "flavorRef": "2",
                    "OS-DCF:diskConfig": "AUTO",
                    "metadata": {
                      "build_config": "core",
                      "meta_key_1": "meta_value_1",
                      "meta_key_2": "meta_value_2"
                    },
                    "networks": [
                      {
                        "uuid": "11111111-1111-1111-1111-111111111111"
                      },
                      {
                        "uuid": "00000000-0000-0000-0000-000000000000"
                      }
                    ],
                    "personality": [
                      {
                        "path": "/root/.csivh",
                        "contents": "VGhpcyBpcyBhIHRlc3QgZmlsZS4="
                      }
                    ]
                  }
                },
                "type": "launch_server"
              },
              "groupConfiguration": {
                "maxEntities": 10,
                "cooldown": 360,
                "name": "testscalinggroup198547",
                "minEntities": 0,
                "metadata": {
                  "gc_meta_key_2": "gc_meta_value_2",
                  "gc_meta_key_1": "gc_meta_value_1"
                }
              },
              "scalingPolicies": [
                {
                  "cooldown": 0,
                  "type": "webhook",
                  "name": "scale up by 1",
                  "change": 1
                }
              ]
            }


        The ``scalingPolicies`` attribute can also be an empty list, or just left
        out entirely.

        Example response body to the above request::

            {
              "group": {
                "launchConfiguration": {
                  "args": {
                    "loadBalancers": [
                      {
                        "port": 8080,
                        "loadBalancerId": 9099
                      }
                    ],
                    "server": {
                      "name": "autoscale_server",
                      "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                      "flavorRef": "2",
                      "OS-DCF:diskConfig": "AUTO",
                      "personality": [
                        {
                          "path": "/root/.csivh",
                          "contents": "VGhpcyBpcyBhIHRlc3QgZmlsZS4="
                        }
                      ],
                      "networks": [
                        {
                          "uuid": "11111111-1111-1111-1111-111111111111"
                        },
                        {
                          "uuid": "00000000-0000-0000-0000-000000000000"
                        }
                      ],
                      "metadata": {
                        "build_config": "core",
                        "meta_key_1": "meta_value_1",
                        "meta_key_2": "meta_value_2"
                      }
                    }
                  },
                  "type": "launch_server"
                },
                "groupConfiguration": {
                  "maxEntities": 10,
                  "cooldown": 360,
                  "name": "testscalinggroup198547",
                  "minEntities": 0,
                  "metadata": {
                    "gc_meta_key_2": "gc_meta_value_2",
                    "gc_meta_key_1": "gc_meta_value_1"
                  }
                },
                "state": {
                  "active": [],
                  "activeCapacity": 0,
                  "desiredCapacity": 0,
                  "paused": false,
                  "pendingCapacity": 0,
                  "name": "testscalinggroup198547"
                },
                "scalingPolicies": [
                  {
                    "name": "scale up by 1",
                    "links": [
                      {
                        "href": "https://ord.autoscale.api.rackspacecloud.com/
                        v1.0/829409/groups/6791761b-821a-4d07-820d-0b2afc7dd7f6/
                        policies/dceb14ac-b2b3-4f06-aac9-a5b6cd5d40e1/",
                        "rel": "self"
                      }
                    ],
                    "cooldown": 0,
                    "type": "webhook",
                    "id": "dceb14ac-b2b3-4f06-aac9-a5b6cd5d40e1",
                    "change": 1
                  }
                ],
                "links": [
                  {
                    "href": "https://ord.autoscale.api.rackspacecloud.com/
                    v1.0/829409/groups/6791761b-821a-4d07-820d-0b2afc7dd7f6/",
                    "rel": "self"
                  }
                ],
                "id": "6791761b-821a-4d07-820d-0b2afc7dd7f6"
              }
            }

        """
        data['groupConfiguration'].setdefault('maxEntities', MAX_ENTITIES)
        data['groupConfiguration'].setdefault('metadata', {})

        if data['groupConfiguration']['minEntities'] > data['groupConfiguration']['maxEntities']:
            raise InvalidMinEntities("minEntities must be less than or equal to maxEntities")

        deferred = get_supervisor().validate_launch_config(
            self.log, self.tenant_id, data['launchConfiguration'])

        deferred.addCallback(
            lambda _: self.store.create_scaling_group(self.log, self.tenant_id,
                                                      data['groupConfiguration'],
                                                      data['launchConfiguration'],
                                                      data.get('scalingPolicies', None)))

        def _do_obey_config_change(result):
            group_id = result['id']
            config = result['groupConfiguration']
            group = self.store.get_scaling_group(self.log, self.tenant_id, group_id)
            d = group.modify_state(partial(controller.obey_config_change, self.log,
                                           transaction_id(request), config))
            return d.addCallback(lambda _: result)

        deferred.addCallback(_do_obey_config_change)

        def _add_to_bobby(result, client):
            d = client.create_group(self.tenant_id, result['id'])
            return d.addCallback(lambda _: result)

        bobby = get_bobby()
        if bobby is not None:
            deferred.addCallback(_add_to_bobby, bobby)

        def _format_output(result):
            uuid = result['id']
            result["state"] = format_state_dict(result["state"])
            request.setHeader(
                "Location", get_autoscale_links(self.tenant_id, uuid, format=None))
            result["links"] = get_autoscale_links(self.tenant_id, uuid)
            linkify_policy_list(result['scalingPolicies'], self.tenant_id, uuid)
            result['scalingPolicies_links'] = get_policies_links(
                result['scalingPolicies'], self.tenant_id, uuid, rel='policies')
            return {"group": result}

        deferred.addCallback(_format_output)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/<string:group_id>/', branch=True)
    def group(self, request, group_id):
        """
        Routes requiring a specific group_id are delegated to
        OtterGroup.
        """
        return OtterGroup(self.store, self.tenant_id, group_id).app.resource()


class OtterGroup(object):
    """
    REST endpoints for managing a specific scaling group.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, group_id):
        self.log = log.bind(system='otter.rest.group',
                            tenant_id=tenant_id,
                            group_id=group_id)
        self.store = store
        self.tenant_id = tenant_id
        self.group_id = group_id

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def view_manifest_config_for_scaling_group(self, request):
        """
        View manifested view of the scaling group configuration, including the
        launch configuration, and the scaling policies.  This data is returned in
        the body of the response in JSON format.

        Example response::


            {
                "group": {
                    "groupConfiguration": {
                        "cooldown": 60,
                        "maxEntities": 0,
                        "metadata": {},
                        "minEntities": 0,
                        "name": "smallest possible launch config group"
                    },
                    "state": {
                        "active": [],
                        "activeCapacity": 0,
                        "desiredCapacity": 0,
                        "paused": false,
                        "pendingCapacity": 0
                    },
                    "id": "605e13f6-1452-4588-b5da-ac6bb468c5bf",
                    "launchConfiguration": {
                        "args": {
                            "server": {}
                        },
                        "type": "launch_server"
                    },
                    "links": [
                        {
                            "href": "https://dfw.autoscale.api.rackspacecloud.com/
                            v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/",
                            "rel": "self"
                        }
                    ],
                    "scalingPolicies": [
                        {
                            "changePercent": -5.5,
                            "cooldown": 1800,
                            "id": "eb0fe1bf-3428-4f34-afd9-a5ac36f60511",
                            "links": [
                                {
                                    "href": "https://dfw.autoscale.api.rackspacecloud.com/
                                    v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/
                                    policies/eb0fe1bf-3428-4f34-afd9-a5ac36f60511/",
                                    "rel": "self"
                                }
                            ],
                            "name": "scale down by 5.5 percent",
                            "type": "webhook"
                        },
                    ]
                }
            }
        """
        def openstack_formatting(data, uuid):
            data["links"] = get_autoscale_links(self.tenant_id, uuid)
            data["state"] = format_state_dict(data["state"])
            linkify_policy_list(data["scalingPolicies"], self.tenant_id, uuid)
            data['scalingPolicies_links'] = get_policies_links(
                data['scalingPolicies'], self.tenant_id, uuid, rel='policies')
            return {"group": data}

        group = self.store.get_scaling_group(self.log, self.tenant_id, self.group_id)
        deferred = group.view_manifest()
        deferred.addCallback(openstack_formatting, group.uuid)
        deferred.addCallback(json.dumps)
        return deferred

    # Feature: Force delete, which stops scaling, deletes all servers for you, then
    #       deletes the scaling group.
    @app.route('/', methods=['DELETE'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def delete_scaling_group(self, request):
        """
        Delete a scaling group if there are no entities belonging to the scaling
        group.  If successful, no response body will be returned.
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id,
                                             self.group_id)
        force = False
        try:
            force_arg = request.args.get('force')[0].lower()
            if force_arg == 'true':
                force = True
            else:
                return defer.fail(InvalidQueryArgument(
                    'Invalid query argument for "limit"'))
        except (IndexError, TypeError):
            # There is no argument
            pass
        if force:
            config = []
            d = group.view_config()

            def update_config(_config):
                _config['minEntities'] = 0
                _config['maxEntities'] = 0
                config.append(_config)
                return group.update_config(_config)
            d.addCallback(update_config)

            def modify_state(_):
                _config = config[0]
                d = group.modify_state(
                    partial(controller.obey_config_change, self.log,
                            transaction_id(request), _config))
                return d
            d.addCallback(modify_state)

            return d.addCallback(lambda _: group.delete_group())
        else:
            return group.delete_group()

    @app.route('/state/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def get_scaling_group_state(self, request):
        """
        Get the current state of the scaling group, including the current set of
        active entities, number of pending entities, and the desired number
        of entities.  This data is returned in the body of the response in JSON format.

        There is no guarantee about the sort order of the list of active entities.

        Example response::

            {
                "group": {
                    "paused": false,
                    "pendingCapacity": 0,
                    "name": "testscalinggroup198547",
                    "active": [],
                    "activeCapacity": 0,
                    "desiredCapacity": 0
                }
            }
        """
        def _format_and_stackify(state):
            return {"group": format_state_dict(state)}

        group = self.store.get_scaling_group(self.log, self.tenant_id, self.group_id)
        deferred = group.view_state()
        deferred.addCallback(_format_and_stackify)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/pause/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def pause_scaling_group(self, request):
        """
        Pause a scaling group.  This means that no scaling policies will get
        executed (execution will be rejected).  This is an idempotent operation -
        pausing an already paused group does nothing.
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id, self.group_id)
        return controller.pause_scaling_group(self.log, transaction_id(request), group)

    @app.route('/resume/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def resume_scaling_group(self, request):
        """
        Resume a scaling group.  This means that scaling policies will now get
        executed as usual.  This is an idempotent operation - resuming an already
        running group does nothing.
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id, self.group_id)
        return controller.resume_scaling_group(self.log, transaction_id(request), group)

    @app.route('/config/')
    def config(self, request):
        """
        config route handled by OtterConfig
        """
        return OtterConfig(self.store, self.tenant_id, self.group_id).app.resource()

    @app.route('/launch/')
    @with_transaction_id()
    def launch(self, request):
        """
        launch route handled by OtterLaunch
        """
        return OtterLaunch(self.store, self.tenant_id, self.group_id).app.resource()

    @app.route('/policies/', branch=True)
    @with_transaction_id()
    def policies(self, request):
        """
        policies routes handled by OtterPolicies
        """
        return OtterPolicies(self.store, self.tenant_id, self.group_id).app.resource()
