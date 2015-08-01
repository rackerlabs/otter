from functools import partial

import attr

from characteristic import attributes

from effect import TypeDispatcher, sync_performer

from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import deferred_performer

from otter.log.intents import merge_effectful_fields
from otter.models.cass import CassScalingGroupServersCache
from otter.util.fp import assoc_obj


@attributes(['tenant_id', 'group_id'])
class GetScalingGroupInfo(object):
    """Get a scaling group and its manifest."""


@deferred_performer
@inlineCallbacks
def perform_get_scaling_group_info(log, store, dispatcher, intent):
    """
    Perform :obj:`GetScalingGroupInfo`.

    :param log: bound log
    :param IScalingGroupCollection store: collection of groups
    :param dispatcher: dispatcher provided by perform
    :param GetScalingGroupInfo intent: the intent
    """
    log = merge_effectful_fields(dispatcher, log)
    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    manifest = yield group.view_manifest(with_policies=False,
                                         with_webhooks=False,
                                         get_deleting=True)
    returnValue((group, manifest))


@attributes(['tenant_id', 'group_id'])
class DeleteGroup(object):
    """
    Delete scaling group
    """


@deferred_performer
def perform_delete_group(log, store, dispatcher, intent):
    """
    Perform `DeleteGroup`
    """
    log = merge_effectful_fields(dispatcher, log)
    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    return group.delete_group()


@attributes(['scaling_group', 'status'])
class UpdateGroupStatus(object):
    """An Effect intent which updates the status of a scaling group."""


@deferred_performer
def perform_update_group_status(dispatcher, ugs_intent):
    """Perform an :obj:`UpdateGroupStatus`."""
    return ugs_intent.scaling_group.update_status(ugs_intent.status)


@attr.s
class UpdateServersCache(object):
    """
    Intent to update servers cache
    """
    tenant_id = attr.ib()
    group_id = attr.ib()
    time = attr.ib()
    servers = attr.ib()


@sync_performer
def perform_update_servers_cache(disp, intent):
    """ Perform :obj:`UpdateServersCache` """
    cache = CassScalingGroupServersCache(intent.tenant_id, intent.group_id)
    return cache.insert_servers(intent.time, intent.servers, True)


@attr.s
class UpdateGroupErrorReasons(object):
    """
    Intent to update group's error reasons
    """
    group = attr.ib()
    reasons = attr.ib()


@deferred_performer
def perform_update_error_reasons(disp, intent):
    return intent.group.update_error_reasons(intent.reasons)


@attr.s
class ModifyGroupStatePaused(object):
    """
    Intent to update group state pause
    """
    group = attr.ib()
    paused = attr.ib()


@deferred_performer
def perform_modify_group_state_paused(disp, intent):
    """ Perform `ModifyGroupStatePaused` """

    def update_paused(_group, state):
        return assoc_obj(state, paused=intent.paused)

    return intent.group.modify_state(update_paused)


def get_model_dispatcher(log, store):
    """Get a dispatcher that can handle all the model-related intents."""
    return TypeDispatcher({
        GetScalingGroupInfo:
            partial(perform_get_scaling_group_info, log, store),
        DeleteGroup: partial(perform_delete_group, log, store),
        UpdateGroupStatus: perform_update_group_status,
        UpdateServersCache: perform_update_servers_cache,
        UpdateGroupErrorReasons: perform_update_error_reasons,
        ModifyGroupStatePaused: perform_modify_group_state_paused
    })
