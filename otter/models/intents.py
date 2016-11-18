from functools import partial

import attr

from characteristic import attributes

from effect import TypeDispatcher, sync_performer

from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import deferred_performer

from otter.log.intents import merge_effectful_fields
from otter.models.cass import CassScalingGroupServersCache
from otter.util.fp import assoc_obj


@attr.s
class GetAllValidGroups(object):
    pass


@deferred_performer
def perform_get_all_valid_groups(store, dispatcher, intent):
    return store.get_all_valid_groups()


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


@attr.s
class DeleteGroup(object):
    """
    Delete scaling group
    """
    tenant_id = attr.ib()
    group_id = attr.ib()


@deferred_performer
def perform_delete_group(log, store, dispatcher, intent):
    """
    Perform `DeleteGroup`
    """
    log = merge_effectful_fields(dispatcher, log)
    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    return group.delete_group()


@attr.s
class GetTenantGroupStates(object):
    """
    Intent to get groups of a tenant. Its performer will return list of
    :obj:`GroupState` objects
    """
    tenant_id = attr.ib()


@attributes(['scaling_group', 'status'])
class UpdateGroupStatus(object):
    """An Effect intent which updates the status of a scaling group."""


@deferred_performer
def perform_update_group_status(dispatcher, ugs_intent):
    """Perform an :obj:`UpdateGroupStatus`."""
    return ugs_intent.scaling_group.update_status(ugs_intent.status)


@attr.s
class LoadAndUpdateGroupStatus(object):
    """
    Intent to load the scaling group object and update its status. This is
    different from :obj:`UpdateGroupStatus` by taking tenant_id and group_id
    instead of group object
    """
    tenant_id = attr.ib()
    group_id = attr.ib()
    status = attr.ib()


@deferred_performer
def perform_load_and_update_group_status(log, store, dispatcher, intent):
    """Perform an :obj:`LoadAndUpdateGroupStatus`."""
    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    return group.update_status(intent.status)


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
    tenant_id = attr.ib()
    group_id = attr.ib()
    reasons = attr.ib()


@deferred_performer
def perform_update_error_reasons(log, store, disp, intent):
    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    return group.update_error_reasons(intent.reasons)


@attr.s
class ModifyGroupStateAttribute(object):
    """
    Intent to update group state's attribute
    """
    tenant_id = attr.ib()
    group_id = attr.ib()
    attribute = attr.ib()
    value = attr.ib()


@deferred_performer
def perform_modify_group_state_attr(log, store, disp, intent):
    """ Perform `ModifyGroupStateAttribute` """

    def update_state(_group, state):
        return assoc_obj(state, **{intent.attribute: intent.value})

    group = store.get_scaling_group(log, intent.tenant_id, intent.group_id)
    return group.modify_state(update_state)


def get_model_dispatcher(log, store):
    """Get a dispatcher that can handle all the model-related intents."""
    return TypeDispatcher({
        GetScalingGroupInfo:
            partial(perform_get_scaling_group_info, log, store),
        DeleteGroup: partial(perform_delete_group, log, store),
        UpdateGroupStatus: perform_update_group_status,
        LoadAndUpdateGroupStatus:
            partial(perform_load_and_update_group_status, log, store),
        UpdateServersCache: perform_update_servers_cache,
        UpdateGroupErrorReasons:
            partial(perform_update_error_reasons, log, store),
        ModifyGroupStateAttribute: partial(perform_modify_group_state_attr,
                                           log, store),
        GetAllValidGroups: partial(perform_get_all_valid_groups, store),
        GetTenantGroupStates:
            deferred_performer(
                lambda d, i: store.list_scaling_group_states(log, i.tenant_id))
    })
