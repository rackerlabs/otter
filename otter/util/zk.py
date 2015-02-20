from kazoo.exceptions import BadVersionError, NodeExistsError, NoNodeError


DELETE_NODE = object()


def create_or_update(kz_client, path, fn, initial):
    """
    Safely create a ZK node, or update one based on its old content.

    Atomically swaps the content of the znode specified by ``path`` to the
    return value of ``fn``. Note that ``fn`` may be called multiple times, and
    thus should be free of side-effects -- this is because a check-and-set is
    repeatedly done to ensure the swap is atomic.

    ``fn`` is of type ``bytes -> bytes``.

    If the znode does not exist, then it will be created with the ``initial``
    value, and any non-existent parent nodes will also be made.

    Inspired by Clojure's ``swap!``.

    :return: A Deferred of the value that was swapped in.
    """

    def create():
        d = kz_client.create(path, initial, makepath=True)
        d.addErrback(_handle(NodeExistsError, check_and_set))
        d.addCallback(lambda r: initial)
        return d

    def content_received(result):
        value, zk_node = result
        new_value = fn(value)
        d = kz_client.set(path, new_value, version=zk_node.version)
        d.addErrback(_handle(BadVersionError, check_and_set))
        return d.addCallback(lambda r: new_value)

    def check_and_set():
        d = kz_client.get(path)
        d.addCallback(content_received)
        d.addErrback(_handle(NoNodeError, create))
        return d

    return create()



def _handle(exc_type, fn):
    """
    Stupid utility function that calls a function only after ensuring that a
    failure wraps the specified exception type.
    """
    def handler(f):
        f.trap(exnc_type)
        return fn()
    return handler
