from functools import partial

from characteristic import attributes

from effect import Effect, TypeDispatcher, parallel, sync_performer
from effect.do import do, do_return

from kazoo.exceptions import NoNodeError, NodeExistsError

from txeffect import deferred_performer

from otter.util.deferredutils import catch_failure


CREATE_OR_SET_LOOP_LIMIT = 50
"""
A limit on the number of times we'll jump between trying to create a node
vs trying to set a node's contents in perform_create_or_set.
"""


@attributes(['path', 'content'])
class CreateOrSet(object):
    """
    Create a node, or if the node already exists, set the content.

    Handles the case where a node gets deleted in between our attempt and
    creating and setting.
    """


class CreateOrSetLoopLimitReachedError(Exception):
    """
    Raised when the number of times trying to create a node in
    :func:`perform_create_or_set` has gone over
    :obj:`CREATE_OR_SET_LOOP_LIMIT`.
    """


@deferred_performer
def perform_create_or_set(kz_client, dispatcher, create_or_set):
    """
    Performer for :obj:`CreateOrSet`. Must be partialed with ``kz_client``.
    """
    path = create_or_set.path
    content = create_or_set.content

    def create(count):
        if count >= CREATE_OR_SET_LOOP_LIMIT:
            raise CreateOrSetLoopLimitReachedError(path)
        d = kz_client.create(path, content, makepath=True)
        d.addErrback(catch_failure(NodeExistsError,
                                   lambda f: set_content(count)))
        return d

    def set_content(count):
        d = kz_client.set(path, content)
        d.addErrback(catch_failure(NoNodeError,
                                   lambda f: create(count + 1)))
        return d.addCallback(lambda r: path)

    return create(0)


@attributes(['path'], apply_with_init=False)
class GetChildrenWithStats(object):
    """
    List children along with their stat information.

    Results in ``[(child_path, :obj:`ZnodeStat`)]``.
    """
    def __init__(self, path):
        self.path = path


@sync_performer
@do
def perform_get_children_with_stats(kz_client, dispatcher, intent):
    """
    Perform :obj:`GetChildrenWithStats`. Must be partialed with ``kz_client``.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param GetChildrenWithStats intent: the intent
    """
    path = intent.path
    children = yield Effect(GetChildren(path))
    stats = yield parallel(Effect(GetStat(path + '/' + p)) for p in children)
    yield do_return([
        c_and_s for c_and_s in zip(children, stats)
        if c_and_s[1] is not None])


@attributes(['path'], apply_with_init=False)
class GetChildren(object):
    """List children."""
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_children(kz_client, dispatcher, intent):
    """Perform a :obj:`GetChildren`."""
    return kz_client.get_children(intent.path)


@attributes(['path'], apply_with_init=False)
class GetStat(object):
    """
    Get the :obj:`ZnodeStat` of a ZK node, or None if the node does not exist.
    """
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_stat(kz_client, dispatcher, intent):
    """Perform a :obj:`GetStat`."""
    return kz_client.exists(intent.path)


@attributes(['path', 'version'])
class DeleteNode(object):
    """Delete a node."""


@deferred_performer
def perform_delete_node(kz_client, dispatcher, intent):
    """Perform :obj:`DeleteNode`.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param DeleteNode intent: the intent
    """
    return kz_client.delete(intent.path, version=intent.version)


def get_zk_dispatcher(kz_client):
    """Get a dispatcher that can support all of the ZooKeeper intents."""
    return TypeDispatcher({
        CreateOrSet:
            partial(perform_create_or_set, kz_client),
        DeleteNode:
            partial(perform_delete_node, kz_client),
        GetChildrenWithStats:
            partial(perform_get_children_with_stats, kz_client),
        GetChildren:
            partial(perform_get_children, kz_client),
        GetStat:
            partial(perform_get_stat, kz_client)
    })
