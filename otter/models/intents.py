from characteristic import attributes

from effect.twisted import deferred_performer


@attributes(['scaling_group', 'modifier'])
class ModifyGroupState(object):
    """
    An Effect intent which indicates that a group state should be updated.
    """


@deferred_performer
def perform_modify_group_state(dispatcher, mgs):
    """Perform a :obj:`ModifyGroupState`."""
    return mgs.scaling_group.modify_state(mgs.modifier)
