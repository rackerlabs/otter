"""
Zookeeper utilities
"""
from txzookeeper.client import ZookeeperClient
from twisted.internet import defer

from otter.util.deferredutils import unwrap_first_error


_zookeeper_client = None

def get_zookeeper_client():
    return _zookeeper_client

def connect_zookeeper_client(servers, timeout):
    global _zookeeper_client

    if _zookeeper_client is not None:
        return defer.succeed(_zookeeper_client)

    _zookeeper_client = ZookeeperClient(servers, timeout)

    deferred = _zookeeper_client.connect()

    def _on_client_connect(client):
        return client.exists('/scaling_group_lock')
    deferred.addCallbacks(_on_client_connect, unwrap_first_error)

    def _maybe_create_path(path):
        if path is None:
            return _zookeeper_client.create('/scaling_group_lock')
        return defer.succeed(True)
    deferred.addCallback(_maybe_create_path)

    return deferred.addCallback(lambda _: _zookeeper_client)
