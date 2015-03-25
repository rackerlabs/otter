from functools import partial

from characteristic import attributes

from effect import TypeDispatcher
from effect.twisted import deferred_performer


@attributes(['path'], apply_with_init=False)
class Create(object):
    """Create a node."""
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_create(kz_client, dispatcher, intent):
    """
    Performer for :obj:`Create`. Must be partialed with ``kz_client``.

    :param Create intent: the intent
    """
    path = intent.path
    return kz_client.create(path, makepath=True)


@attributes(['path'], apply_with_init=False)
class GetChildren(object):
    """List children."""
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_children(kz_client, dispatcher, intent):
    """
    Perform :obj:`GetChildren`. Must be partialed with ``kz_client``.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param GetChildren intent: the intent
    """
    path = intent.path
    return kz_client.get_children(path)


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
        Create:
            partial(perform_create, kz_client),
        DeleteNode:
            partial(perform_delete_node, kz_client),
        GetChildren:
            partial(perform_get_children, kz_client),
    })
