"""
Autoscale REST endpoints having to do with a group or collection of groups
(/tenantId/groups and /tenantId/groups/groupId)
"""
import json

from functools import partial

from twisted.internet.defer import gatherResults, succeed

from txeffect import perform

from otter import controller
from otter.controller import GroupPausedError
from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import get_convergence_starter
from otter.effect_dispatcher import get_working_cql_dispatcher
from otter.json_schema.group_schemas import (
    MAX_ENTITIES,
    validate_launch_config_servicenet,
)
from otter.json_schema.rest_schemas import create_group_request
from otter.log import log
from otter.models.cass import CassScalingGroupServersCache
from otter.models.interface import ScalingGroupStatus
from otter.rest.bobby import get_bobby
from otter.rest.configs import (
    OtterConfig,
    OtterLaunch,
    normalize_launch_config
)
from otter.rest.decorators import (
    InvalidQueryArgument,
    fails_with,
    paginatable,
    succeeds_with,
    validate_body,
    with_transaction_id,
)
from otter.rest.errors import InvalidMinEntities, exception_codes
from otter.rest.otterapp import OtterApp
from otter.rest.policies import OtterPolicies, linkify_policy_list
from otter.rest.webhooks import _format_webhook
from otter.supervisor import get_supervisor
from otter.util.config import config_value
from otter.util.http import (
    get_autoscale_links,
    get_groups_links,
    get_policies_links,
    get_webhooks_links,
    transaction_id,
)


def format_state_dict(state, active=None):
    """
    Takes a state returned by the model and reformats it to be returned as a
    response.

    :param state: a :class:`otter.models.interface.GroupState` object
    :param dict active: Active servers used when provided
        instead of state.active

    :return: a ``dict`` that looks like what should be respond by the API
        response when getting state
    """
    if active is not None:
        desired = state.desired
        pending = state.desired - len(active)
    else:
        pending = len(state.pending)
        desired = len(state.active) + pending
        active = state.active
    state_json = {
        'activeCapacity': len(active),
        'pendingCapacity': pending,
        'desiredCapacity': desired,
        'name': state.group_name,
        'paused': state.paused,
        'status': state.status.name,
        'active': [
            {
                'id': key,
                'links': server_blob['links'],
            } for key, server_blob in active.iteritems()
        ]
    }
    if state.status == ScalingGroupStatus.ERROR:
        state_json['errors'] = [
            {'message': reason} for reason in state.error_reasons]
    return state_json


def extract_bool_arg(request, key, default=False):
    """
    Get bool query arg from the request

    :param request: :class:`twisted.web.http.Request` object
    :param str key: The argument key
    :param bool default: The default value to return if key is not there
    """
    if key in request.args:
        value = request.args[key][0].lower()
        if value == 'true':
            return True
        elif value == 'false':
            return False
        else:
            raise InvalidQueryArgument(
                'Invalid "{}" query argument: "{}". '
                'Must be "true" or "false". '
                'Defaults to "{}" if not provided'
                .format(key, value, str(default).lower()))
    else:
        return default


class OtterGroups(object):
    """
    REST endpoints for managing scaling groups.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, dispatcher):
        self.log = log.bind(system='otter.rest.groups',
                            tenant_id=tenant_id)
        self.store = store
        self.tenant_id = tenant_id
        self.dispatcher = dispatcher

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    @paginatable
    def list_all_scaling_groups(self, request, paginate):
        """
        Lists all the autoscaling groups and their states per for a given
        tenant ID.

        Example response::

            {
                "groups": [
                    {
                        "id": "e41380ae-173c-4b40-848a-25c16d7fa83d",
                        "links": [
                            {
                                "href": "https://dfw.autoscale.api
                                .rackspacecloud.com/
                                v1.0/676873/
                                groups/e41380ae-173c-4b40-848a-25c16d7fa83d/",
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
                                "href": "https://dfw.autoscale.api
                                .rackspacecloud.com/
                                v1.0/676873/
                                groups/f82bb000-f451-40c8-9dc3-6919097d2f7e/",
                                "rel": "self"
                            }
                        ]
                    }
                ],
                "groups_links": []
            }


        """

        def format_list(results):
            group_states, actives = results
            groups = [{
                'id': state.group_id,
                'links': get_autoscale_links(state.tenant_id, state.group_id),
                'state': format_state_dict(state, active)
            } for state, active in zip(group_states, actives)]
            return {
                "groups": groups,
                "groups_links": get_groups_links(
                    groups, self.tenant_id, None, **paginate)
            }

        def fetch_active_caches(group_states):
            if not tenant_is_enabled(self.tenant_id, config_value):
                return group_states, [None] * len(group_states)
            d = gatherResults(
                [get_active_cache(
                    self.store.reactor, self.store.connection, self.tenant_id,
                    state.group_id)
                 for state in group_states])
            return d.addCallback(lambda cache: (group_states, cache))

        deferred = self.store.list_scaling_group_states(
            self.log, self.tenant_id, **paginate)
        deferred.addCallback(fetch_active_caches)
        deferred.addCallback(format_list)
        deferred.addCallback(json.dumps)
        return deferred

    # -------------------------- CRD a scaling group -------------------------
    # (CRD = CRUD - U, because updating happens at suburls - so you can update
    # different parts)

    @app.route('/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(201)
    @validate_body(create_group_request)
    def create_new_scaling_group(self, request, data):
        """
        Create a new scaling group, given the general scaling group
        configuration, launch configuration, and optional scaling policies.
        This data provided in the request body in JSON format. If
        successful, the created group in JSON format containing id and links
        is returned.

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


        The ``scalingPolicies`` attribute can also be an empty list, or just
        left out entirely.

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
        group_cfg = data['groupConfiguration']

        group_cfg.setdefault('maxEntities', MAX_ENTITIES)
        group_cfg.setdefault('metadata', {})

        if group_cfg['minEntities'] > group_cfg['maxEntities']:
            raise InvalidMinEntities(
                "minEntities must be less than or equal to maxEntities")

        validate_launch_config_servicenet(data['launchConfiguration'])

        deferred = get_supervisor().validate_launch_config(
            self.log, self.tenant_id, data['launchConfiguration'])

        deferred.addCallback(
            lambda _: self.store.create_scaling_group(
                self.log, self.tenant_id,
                group_cfg,
                normalize_launch_config(data['launchConfiguration']),
                data.get('scalingPolicies', None)))

        def _do_obey_config_change(result):
            group_id = result['id']
            config = result['groupConfiguration']
            launch = result['launchConfiguration']
            group = self.store.get_scaling_group(
                self.log, self.tenant_id, group_id)
            d = group.modify_state(partial(
                controller.obey_config_change, self.log,
                transaction_id(request), config, launch_config=launch),
                modify_state_reason='create_new_scaling_group')
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
                "Location",
                get_autoscale_links(self.tenant_id, uuid, format=None))
            result["links"] = get_autoscale_links(self.tenant_id, uuid)
            linkify_policy_list(
                result['scalingPolicies'], self.tenant_id, uuid)
            result['scalingPolicies_links'] = get_policies_links(
                result['scalingPolicies'],
                self.tenant_id, uuid, rel='policies')
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
        return OtterGroup(self.store, self.tenant_id,
                          group_id, self.dispatcher).app.resource()


def get_active_cache(reactor, connection, tenant_id, group_id):
    """
    Get active servers from servers cache table
    """
    eff = CassScalingGroupServersCache(tenant_id, group_id).get_servers(True)
    disp = get_working_cql_dispatcher(reactor, connection)
    d = perform(disp, eff)
    return d.addCallback(lambda (servers, _): {s['id']: s for s in servers})


class OtterGroup(object):
    """
    REST endpoints for managing a specific scaling group.
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, group_id, dispatcher):
        self.log = log.bind(system='otter.rest.group',
                            tenant_id=tenant_id,
                            scaling_group_id=group_id)
        self.store = store
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.dispatcher = dispatcher

    def with_active_cache(self, get_func, *args, **kwargs):
        """
        Return result of `get_func` and active cache from servers table
        if this is convergence enabled tenant
        """
        if tenant_is_enabled(self.tenant_id, config_value):
            cache_d = get_active_cache(
                self.store.reactor, self.store.connection, self.tenant_id,
                self.group_id)
        else:
            cache_d = succeed(None)
        return gatherResults([get_func(*args, **kwargs), cache_d],
                             consumeErrors=True)

    @app.route('/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def view_manifest_config_for_scaling_group(self, request):
        """
        View manifested view of the scaling group configuration, including the
        launch configuration, and the scaling policies.  This data is
        returned in the body of the response in JSON format.

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
                            "href": "https://dfw.autoscale.api.
                            rackspacecloud.com/
                            v1.0/676873
                            /groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/",
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
                                    "href": "https://dfw.autoscale.api.
                                    rackspacecloud.com/
                                    v1.0/676873/groups/
                                    605e13f6-1452-4588-b5da-ac6bb468c5bf/
                                    policies/
                                    eb0fe1bf-3428-4f34-afd9-a5ac36f60511/",
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
        def with_webhooks(_request):
            return ('webhooks' in _request.args and
                    _request.args['webhooks'][0].lower() == 'true')

        def add_webhooks_links(policies):
            for policy in policies:
                webhook_list = [_format_webhook(webhook_model, self.tenant_id,
                                                self.group_id, policy['id'])
                                for webhook_model in policy['webhooks']]
                policy['webhooks'] = webhook_list
                policy['webhooks_links'] = get_webhooks_links(
                    webhook_list,
                    self.tenant_id,
                    self.group_id,
                    policy['id'],
                    rel='webhooks')

        def openstack_formatting(results):
            data, active = results
            data["links"] = get_autoscale_links(self.tenant_id, self.group_id)
            data["state"] = format_state_dict(data["state"], active)
            linkify_policy_list(
                data["scalingPolicies"], self.tenant_id, self.group_id)
            data['scalingPolicies_links'] = get_policies_links(
                data['scalingPolicies'], self.tenant_id, self.group_id,
                rel='policies')
            if with_webhooks(request):
                add_webhooks_links(data["scalingPolicies"])
            return {"group": data}

        group = self.store.get_scaling_group(
            self.log, self.tenant_id, self.group_id)
        deferred = self.with_active_cache(
            group.view_manifest, with_webhooks=with_webhooks(request))
        deferred.addCallback(openstack_formatting)
        deferred.addCallback(json.dumps)
        return deferred

    # Feature: Force delete, which stops scaling, deletes all servers for
    #       you, then deletes the scaling group.
    @app.route('/', methods=['DELETE'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def delete_scaling_group(self, request):
        """
        Delete a scaling group if there are no entities belonging to the
        scaling group.  If successful, no response body will be returned.
        """
        group = self.store.get_scaling_group(self.log, self.tenant_id,
                                             self.group_id)
        force = extract_bool_arg(request, 'force', False)
        return controller.delete_group(
            log, transaction_id(request), group, force)

    @app.route('/state/', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def get_scaling_group_state(self, request):
        """
        Get the current state of the scaling group, including the current set
        of active entities, number of pending entities, and the desired
        number of entities.  This data is returned in the body of the
        response in JSON format.

        There is no guarantee about the sort order of the list of active
        entities.

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
        def _format_and_stackify(results):
            state, active = results
            return {"group": format_state_dict(state, active)}

        group = self.store.get_scaling_group(
            self.log, self.tenant_id, self.group_id)
        deferred = self.with_active_cache(group.view_state)
        deferred.addCallback(_format_and_stackify)
        deferred.addCallback(json.dumps)
        return deferred

    @app.route('/converge/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def converge_scaling_group(self, request):
        """
        Trigger convergence on given scaling group
        """

        def is_group_paused(group, state):
            if state.paused:
                raise GroupPausedError(group.tenant_id, group.uuid, "converge")
            return state

        if tenant_is_enabled(self.tenant_id, config_value):
            group = self.store.get_scaling_group(
                self.log, self.tenant_id, self.group_id)
            cs = get_convergence_starter()
            d = group.modify_state(is_group_paused)
            return d.addCallback(
                lambda _: cs.start_convergence(self.log, self.tenant_id,
                                               self.group_id))
        else:
            request.setResponseCode(404)

    @app.route('/pause/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def pause_scaling_group(self, request):
        """
        Pause a scaling group.  This means that no scaling policies will get
        executed (execution will be rejected).  This is an idempotent
        operation - pausing an already paused group does nothing.
        """
        group = self.store.get_scaling_group(
            self.log, self.tenant_id, self.group_id)
        return controller.pause_scaling_group(
            self.log, transaction_id(request), group, self.dispatcher)

    @app.route('/resume/', methods=['POST'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(204)
    def resume_scaling_group(self, request):
        """
        Resume a scaling group.  This means that scaling policies will now get
        executed as usual.  This is an idempotent operation - resuming an
        already running group does nothing.
        """
        group = self.store.get_scaling_group(
            self.log, self.tenant_id, self.group_id)
        return controller.resume_scaling_group(
            self.log, transaction_id(request), group)

    @app.route('/servers/', branch=True)
    def servers(self, request):
        """
        servers/ route handling
        """
        servers = OtterServers(self.store, self.tenant_id, self.group_id)
        return servers.app.resource()

    @app.route('/config/')
    def config(self, request):
        """
        config route handled by OtterConfig
        """
        config = OtterConfig(self.store, self.tenant_id, self.group_id)
        return config.app.resource()

    @app.route('/launch/')
    def launch(self, request):
        """
        launch route handled by OtterLaunch
        """
        launch = OtterLaunch(self.store, self.tenant_id, self.group_id)
        return launch.app.resource()

    @app.route('/policies/', branch=True)
    def policies(self, request):
        """
        policies routes handled by OtterPolicies
        """
        policies = OtterPolicies(self.store, self.tenant_id, self.group_id)
        return policies.app.resource()


class OtterServers(object):
    """
    REST endpoints to access servers in a scaling group
    """
    app = OtterApp()

    def __init__(self, store, tenant_id, scaling_group_id):
        self.log = log.bind(system='otter.rest.group.servers',
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
    def list_servers(self, request, paginate):
        """
        Get a list of servers in the group.
        """
        raise NotImplementedError

    @app.route('/<string:server_id>', methods=['GET'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(200)
    def get_server(self, request, server_id):
        """
        Get particular server from the group
        """
        raise NotImplementedError

    @app.route('/<string:server_id>/', methods=['DELETE'])
    @with_transaction_id()
    @fails_with(exception_codes)
    @succeeds_with(202)
    def delete_server(self, request, server_id):
        """
        Delete a server from the group.
        """
        group = self.store.get_scaling_group(
            self.log, self.tenant_id, self.scaling_group_id)
        d = group.modify_state(
            partial(controller.remove_server_from_group,
                    self.log.bind(server_id=server_id),
                    transaction_id(request), server_id,
                    extract_bool_arg(request, 'replace', True),
                    extract_bool_arg(request, 'purge', True)),
            modify_state_reason='delete_server')
        return d
