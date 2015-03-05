from functools import partial

from characteristic import attributes

from effect import TypeDispatcher
from effect.twisted import deferred_performer

from twisted.internet.defer import inlineCallbacks, returnValue


@attributes(['scaling_group', 'modifier'])
class ModifyGroupState(object):
    """
    An Effect intent which indicates that a group state should be updated.
    """


@deferred_performer
def perform_modify_group_state(dispatcher, mgs_intent):
    """Perform a :obj:`ModifyGroupState`."""
    return mgs_intent.scaling_group.modify_state(mgs_intent.modifier)


@attributes(['tenant_id', 'group_id'])
class GetScalingGroupInfo(object):
    """Look up a scaling group, along with its `state` and launch config."""


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
    group = yield store.get_scaling_group(
        log, intent.tenant_id, intent.group_id)
    state = yield group.view_state()
    lc = yield group.view_launch_config()
    returnValue((group, state, lc))


def get_cassandra_dispatcher(log, store):
    """Get a dispatcher that can handle all the cass-related intents."""
    return TypeDispatcher({
        ModifyGroupState:
            perform_modify_group_state,
        GetScalingGroupInfo:
            partial(perform_get_scaling_group_info, log, store)
    })
