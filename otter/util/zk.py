from kazoo.exceptions import NoNodeError, NodeExistsError


def create_or_set(kz_client, path, content):
    """
    Create a node, or if the node already exists, set the content.

    Handles the case where a node gets deleted in between our attempt and
    creating and setting.
    """
    def create():
        d = kz_client.create(path, content, makepath=True)
        d.addErrback(_handle(NodeExistsError, set_content))
        return d

    def set_content():
        d = kz_client.set(path, content)
        d.addErrback(_handle(NoNodeError, create))
        return d.addCallback(lambda r: path)

    return create()


def _handle(exc_type, fn):
    """
    Stupid utility function that calls a function only after ensuring that a
    failure wraps the specified exception type.
    """
    def handler(f):
        f.trap(exc_type)
        return fn()
    return handler
