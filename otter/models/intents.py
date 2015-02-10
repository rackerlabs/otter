from characteristic import attributes

from effect.twisted import deferred_performer


@attributes(['scaling_group', 'group_state'])
class ModifyGroupState(object):
    """
    An Effect intent which indicates that a group state should be updated.
    """


@deferred_performer
def perform_modify_group_state(mgs):
    """Perform an :obj:`UpdateGroupState`."""
    return mgs.scaling_group.modify_state(lambda: mgs.state)
