"""
Utility for interacting with the Inventory system through the REST API
"""

import json
from cStringIO import StringIO
from urlparse import urljoin

from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import FileBodyProducer, Agent

from otter import config


_agent = None

SCALING_GROUP_SERVICE_NAME = 'autoscale_group'


class InvalidEntityError(Exception):
    """
    Exception raised when an invalid entity is tagged
    """
    pass


class InventoryError(Exception):
    """
    Non-specific error from the inventory system
    """
    pass


def add_entity_to_scaling_group(tenant_id, entity_id, scaling_group_id,
                                entity_type='servers',
                                agent=None):
    """
    Tag an entity with a particular scaling group id service tag.  By default,
    will be tagging a server.

    :param tenant_id: the tenant ID of the scaling groups
    :type tenant_id: ``str``

    :param entity_id: the UUID of the entity
    :type entity_id: ``str``

    :param tags: a list of service tags to add - in all likelyhood, just the
        the UUID of the scaling group the entity should belong to
    :type tags: ``str``

    :param entity_type: the type of the entity (defaults to servers)
    :type entity_type: ``str``

    :param agent: the agent to use to connect to the inventory system
    :type agent: :class:`twisted.web.client.Agent`

    :return: None

    :raises:
    """
    if agent is None:
        agent = _get_agent()

    path = '/{tenant}/{entity_type}/{entity_id}/service_tags/{name}/'.format(
        tenant=tenant_id, entity_id=entity_id,
        entity_type=entity_type, name=SCALING_GROUP_SERVICE_NAME)
    body = json.dumps([scaling_group_id])

    deferred = agent.request(
        method="POST", uri=urljoin(config.INVENTORY_URL, path),
        bodyProducer=FileBodyProducer(StringIO(body)))
    deferred.addCallback(_process_response, {
        404: InvalidEntityError("No such {0} {1} for tenant {2}".format(
                entity_type, entity_id, tenant_id)),
        403: InventoryError("Unauthorized to make changes for {0}".format(
                SCALING_GROUP_SERVICE_NAME))
    })
    return deferred


def get_entities_in_scaling_group(tenant_id, scaling_group_id,
                                  entity_type='servers',
                                  agent=None):
    """
    List all the entities of one particular entity type that are in scaling
    group of the given id.

    :param tenant_id: the tenant ID of the scaling groups
    :type tenant_id: ``str``

    :param scaling_group_id: the UUID of the scaling group
    :type scaling_group_id: ``str``

    :param entity_type: the type of the entity (defaults to servers)
    :type entity_type: ``str``

    :param agent: the agent to use to connect to the inventory system
    :type agent: :class:`twisted.web.client.Agent`

    :return: list of entities in the following format::
        [
            {
                "id: "3098235-15023629406",
                "_links": {
                    "canonical": "http://dfw.nova.rackspace.com/blah"
                    "inventory": "http://blahblahblah"
                }
            },
            ...
        ]

    :rtype: ``list`` of ``dicts``

    :raises: :class:`InventoryError` if the inventory system does not
        recognize the entity type or if the tenant id is invalid
    """
    if agent is None:
        agent = _get_agent()

    # not the most endpoint to get entities for one particular service tag -
    # search would probably be better when the endpoint is implemented
    path = '/{tenant}/{entity_type}/service_tags/{service_name}/'.format(
        tenant=tenant_id, entity_type=entity_type,
        service_name=SCALING_GROUP_SERVICE_NAME)

    def _cb(result):
        if scaling_group_id in result[entity_type]:
            return result[entity_type][scaling_group_id]
        return []  # no entities tagged with the scaling group id

    deferred = agent.request(method="GET",
                             uri=urljoin(config.INVENTORY_URL + path))
    deferred.addCallback(_process_response, {
            404: InventoryError("Invalid entity type {0} or tenant {1}".format(
                    entity_type, tenant_id))
        })
    return deferred.addCallback(_cb)


class _BodyReceiver(Protocol):
    def __init__(self):
        self.finish = Deferred()
        self._data = StringIO()

    def dataReceived(self, data):
        self._data.write(data)

    def connectionLost(self, reason):
        self.finish.callback(self._data.getvalue())


def _get_agent():
    """
    Get a default agent
    """
    global _agent
    if _agent is None:
        import reactor
        _agent = Agent(reactor)
    return _agent


def _process_response(response, error_mapping=None):
    """
    Take a response and processes the body and the status code.  If the status
    code is 200, attempts to parse the data as JSON and returns the JSON blob.
    If the status i and if the code is unexp
    """
    error_mapping = error_mapping or None

    if response.code == 204:
        return None

    protocol = _BodyReceiver()
    response.deliverBody(protocol)

    if response.code == 200:
        return protocol.finish.addCallback(json.loads)
    elif response.code in error_mapping:
        raise error_mapping[response.code]
    else:
        def raise_error(result):
            raise InventoryError(result)
        return protocol.finish.addCallback(raise_error)
