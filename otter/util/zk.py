from functools import partial

from characteristic import attributes
from effect.twisted import deferred_performer

from kazoo.exceptions import NoNodeError, NodeExistsError

from twisted.internet.defer import gatherResults


@attributes(['path', 'content'], apply_with_init=False)
class CreateOrSet(object):
    """
    Create a node, or if the node already exists, set the content.

    Handles the case where a node gets deleted in between our attempt and
    creating and setting.
    """
    def __init__(self, path, content):
        self.path = path
        self.content = content


@deferred_performer
def perform_create_or_set(kz_client, dispatcher, create_or_set):
    """
    Performer for :obj:`CreateOrSet`. Must be partialed with ``kz_client``.
    """
    path = create_or_set.path
    content = create_or_set.content

    def create():
        d = kz_client.create(path, content, makepath=True)
        d.addErrback(_handle(NodeExistsError, set_content))
        return d

    def set_content():
        d = kz_client.set(path, content)
        d.addErrback(_handle(NoNodeError, create))
        return d.addCallback(lambda r: path)

    return create()


@attributes(['path'])
class GetChildrenWithStats(object):
    """
    List children along with their stat information.

    Results in ``[(child_path, :obj:`ZnodeStat`)]``.
    """


def get_children_with_stats(kz_client, path):
    """
    Perform :obj:`GetChildrenWithStats`. Must be partialed with ``kz_client``.
    """
    # path = get_children_with_stats.path
    children = kz_client.get_children(path)

    def got_children(children):
        ds = [
            kz_client.exists(path + '/' + child).addCallback(
                lambda r, child=child: (child, r) if r is not None else None)
            for child in children
        ]
        return gatherResults(ds)
    children.addCallback(got_children)
    children.addCallback(partial(filter, None))
    return children


def _handle(exc_type, fn):
    """
    Stupid utility function that calls a function only after ensuring that a
    failure wraps the specified exception type.
    """
    def handler(f):
        f.trap(exc_type)
        return fn()
    return handler
