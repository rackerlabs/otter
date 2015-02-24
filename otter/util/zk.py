from functools import partial

from characteristic import attributes
from effect.twisted import deferred_performer

from kazoo.exceptions import NoNodeError, NodeExistsError

from twisted.internet.defer import gatherResults


@attributes(['path', 'content'])
class CreateOrSet(object):
    """
    Create a node, or if the node already exists, set the content.

    Handles the case where a node gets deleted in between our attempt and
    creating and setting.
    """


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


@attributes(['path'], apply_with_init=False)
class GetChildrenWithStats(object):
    """
    List children along with their stat information.

    Results in ``[(child_path, :obj:`ZnodeStat`)]``.
    """
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_children_with_stats(kz_client, dispatcher, intent):
    """
    Perform :obj:`GetChildrenWithStats`. Must be partialed with ``kz_client``.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param GetChildrenWithStats intent: the intent
    """
    path = intent.path
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
    kz_client.delete(intent.path, version=intent.version)


def _handle(exc_type, fn):
    """
    Stupid utility function that calls a function only after ensuring that a
    failure wraps the specified exception type.
    """
    def handler(f):
        f.trap(exc_type)
        return fn()
    return handler
