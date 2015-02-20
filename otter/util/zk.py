from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError


DELETE_NODE = object()


def create_or_update(kz_client, path, fn, initial):
    """
    Safely create a ZK node, or update one based on its current content.

    If the node doesn't exist, it will be created with ``initial``.  If it does
    exist, the new content will be determined by calling ``fn`` with the old
    content. Note that ``fn`` may be called multiple times, and thus should be
    free of side-effects -- this is because a check-and-set is repeatedly done
    to ensure the operation is atomic.

    :param kz_client: Kazoo client
    :param path: path to the ZK node
    :param fn: function of ``bytes -> bytes``.
    :param initial: the initial value to set if the node does not exist.
    :return: A Deferred of the new value -- that is, the result of ``fn`` that
        was actually used.
    """

    def create():
        d = kz_client.create(path, initial, makepath=True)
        d.addCallback(lambda r: initial)
        d.addErrback(_handle(NodeExistsError, check_and_set))
        return d

    def check_and_set():
        d = kz_client.get(path)
        d.addCallback(content_received)
        d.addErrback(_handle(NoNodeError, create))
        return d

    def content_received(result):
        value, zk_node = result
        new_value = fn(value)
        d = kz_client.set(path, new_value, version=zk_node.version)
        d.addCallback(lambda r: new_value)
        d.addErrback(_handle(BadVersionError, check_and_set))
        d.addErrback(_handle(NoNodeError, create))
        return d

    return create()


def update_or_delete(kz_client, path, fn):
    """
    Safely update or delete a ZK node that already exists based on its current
    content.

    The new content will be determined by calling ``fn`` with the old
    content. Note that ``fn`` may be called multiple times, and thus should be
    free of side-effects -- this is because a check-and-set is repeatedly done
    to ensure the operation is atomic.

    If ``fn`` returns ``DELETE_NODE``, the ZK node will be deleted.

    :param kz_client: Kazoo client
    :param path: path to the ZK node
    :param fn: function of ``bytes -> bytes | DELETE_NODE``.
    :return: A Deferred of the new value -- that is, the result of ``fn`` that
        was actually used.
    """
    def check_and_set():
        d = kz_client.get(path)
        d.addCallback(content_received)
        return d

    def content_received(result):
        value, zk_node = result
        new_value = fn(value)
        if new_value is DELETE_NODE:
            d = kz_client.delete(path, version=zk_node.version)
        else:
            d = kz_client.set(path, new_value, version=zk_node.version)
        d.addCallback(lambda r: new_value)
        d.addErrback(_handle(BadVersionError, check_and_set))
        return d

    return check_and_set()


def _handle(exc_type, fn):
    """
    Stupid utility function that calls a function only after ensuring that a
    failure wraps the specified exception type.
    """
    def handler(f):
        f.trap(exc_type)
        return fn()
    return handler
