from functools import partial
from operator import itemgetter

import attr

from characteristic import Attribute, attributes

from effect import catch, raise_

import six

from toolz.functoolz import identity
from toolz.itertoolz import concat

from otter.cloud_client import cloudfeeds as cf
from otter.cloud_client import (
    log_success_response,
    match_errors,
    only_json_api_errors,
    regex,
    service_request)
from otter.constants import ServiceType
from otter.util.http import APIError, append_segments, try_json_with_keys
from otter.util.pure_http import has_code


# ----- CLB requests and error parsing -----

_CLB_IMMUTABLE_PATTERN = regex(
    "Load\s*Balancer '\d+' has a status of '[^']+' and is considered "
    "immutable")
_CLB_NOT_ACTIVE_PATTERN = regex("Load\s*Balancer is not ACTIVE")
_CLB_DELETED_PATTERN = regex(
    "(Load\s*Balancer '\d+' has a status of 'PENDING_DELETE' and is|"
    "The load balancer is deleted and) considered immutable")
_CLB_MARKED_DELETED_PATTERN = regex(
    "The load\s*balancer is marked as deleted")
_CLB_NO_SUCH_NODE_PATTERN = regex(
    "Node with id #\d+ not found for load\s*balancer #\d+$")
_CLB_NO_SUCH_LB_PATTERN = regex(
    "Load\s*balancer not found")
_CLB_DUPLICATE_NODES_PATTERN = regex(
    "Duplicate nodes detected. One or more nodes already configured "
    "on load\s*balancer")
_CLB_NODE_LIMIT_PATTERN = regex(
    "Nodes must not exceed (\d+) per load\s*balancer")
_CLB_NODE_REMOVED_PATTERN = regex(
    "Node ids ((?:\d+,)*(?:\d+)) are not a part of your load\s*balancer")
_CLB_OVER_LIMIT_PATTERN = regex("OverLimit Retry\.{3}")


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBImmutableError(Exception):
    """
    Error to be raised when the CLB is in some status that causes is to be
    temporarily immutable.

    This exception is _not_ used when the status is PENDING_DELETE. See
    :obj:`CLBDeletedError`.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBNotFoundError(Exception):
    """A CLB doesn't exist. Superclass of other, more specific exceptions."""


class CLBDeletedError(CLBNotFoundError):
    """
    Error to be raised when the CLB has been deleted or is being deleted.
    This is distinct from it not existing.
    """


class NoSuchCLBError(CLBNotFoundError):
    """
    Error to be raised when the CLB never existed in the first place (or it
    has been deleted so long that there is no longer a record of it).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type),
             Attribute('node_id', instance_of=six.text_type)])
class NoSuchCLBNodeError(Exception):
    """
    Error to be raised when attempting to modify a CLB node that no longer
    exists.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBNotActiveError(Exception):
    """
    Error to be raised when a CLB is not ACTIVE (and we have no more
    information about what its actual state is).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBRateLimitError(Exception):
    """
    Error to be raised when CLB returns 413 (rate limiting).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBDuplicateNodesError(Exception):
    """
    Error to be raised only when adding one or more nodes to a CLB whose
    address and port are mapped on the CLB.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type),
             Attribute("node_limit", instance_of=int)])
class CLBNodeLimitError(Exception):
    """
    Error to be raised only when adding one or more nodes to a CLB: adding
    that number of nodes would exceed the maximum number of nodes allowed on
    the CLB.
    """


@attr.s
class CLBPartialNodesRemoved(Exception):
    """
    Exception raised when only some of the nodes are removed.

    :ivar lb_id: CLB ID
    :type: :obj:`six.text_type`
    :ivar list not_removed_node_ids: List of node_ids not removed where each
        node_id is :obj:`six.text_type`
    :ivar list removed_node_ids: List of node_ids removed where each node_id
        is :obj:`six.text_type`
    """
    lb_id = attr.ib(validator=attr.validators.instance_of(six.text_type))
    not_removed_node_ids = attr.ib(validator=attr.validators.instance_of(list))
    removed_node_ids = attr.ib(validator=attr.validators.instance_of(list))


def _expand_clb_matches(matches_tuples, lb_id, node_id=None):
    """
    All CLB messages have only the keys ("message",), and the exception tpye
    takes a load balancer ID and maybe a node ID.  So expand a tuple that looks
    like:

    (code, pattern, exc_type)

    to

    (code, ("message",), pattern, partial(exc_type, lb_id=lb_id))

    and maybe the partial will include the node ID too if it's provided.
    """
    params = {"lb_id": six.text_type(lb_id)}
    if node_id is not None:
        params["node_id"] = six.text_type(node_id)

    return [(m[0], ("message",), m[1], partial(m[2], **params))
            for m in matches_tuples]


def _process_clb_api_error(api_error_code, json_body, lb_id):
    """
    Attempt to parse generic CLB API error messages, and raise recognized
    exceptions in their place.

    :param int api_error_code: The status code from the HTTP request
    :param dict json_body: The error message, parsed as a JSON dict.
    :param string lb_id: The load balancer ID

    :raises: :class:`CLBImmutableError`, :class:`CLBDeletedError`,
        :class:`NoSuchCLBError`, :class:`APIError` by itself
    """
    mappings = (
        # overLimit is different than the other CLB messages because it's
        # produced by repose
        [(413, ("overLimit", "message"), _CLB_OVER_LIMIT_PATTERN,
          partial(CLBRateLimitError, lb_id=six.text_type(lb_id)))] +
        _expand_clb_matches(
            [(422, _CLB_DELETED_PATTERN, CLBDeletedError),
             (410, _CLB_MARKED_DELETED_PATTERN, CLBDeletedError),
             (422, _CLB_IMMUTABLE_PATTERN, CLBImmutableError),
             (422, _CLB_NOT_ACTIVE_PATTERN, CLBNotActiveError),
             (404, _CLB_NO_SUCH_LB_PATTERN, NoSuchCLBError)],
            lb_id))
    return match_errors(mappings, api_error_code, json_body)


def add_clb_nodes(lb_id, nodes):
    """
    Generate effect to add one or more nodes to a load balancer.

    Note: This is not correctly documented in the load balancer documentation -
    it is documented as "Add Node" (singular), but the examples show multiple
    nodes being added.

    :param str lb_id: The load balancer ID to add the nodes to
    :param list nodes: A list of node dictionaries that each look like::

        {
            "address": "valid ip address",
            "port": 80,
            "condition": "ENABLED",
            "weight": 1,
            "type": "PRIMARY"
        }

        (weight and type are optional)

    :return: :class:`ServiceRequest` effect

    :raises: :class:`CLBImmutableError`, :class:`CLBDeletedError`,
        :class:`NoSuchCLBError`, :class:`CLBDuplicateNodesError`,
        :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'POST',
        append_segments('loadbalancers', lb_id, 'nodes'),
        data={'nodes': nodes},
        success_pred=has_code(202))

    @only_json_api_errors
    def _parse_known_errors(code, json_body):
        mappings = _expand_clb_matches(
            [(422, _CLB_DUPLICATE_NODES_PATTERN, CLBDuplicateNodesError)],
            lb_id)
        match_errors(mappings, code, json_body)
        _process_clb_api_error(code, json_body, lb_id)
        process_nodelimit_error(code, json_body, lb_id)

    return eff.on(error=_parse_known_errors).on(
        log_success_response('request-add-clb-nodes', identity))


def process_nodelimit_error(code, json_body, lb_id):
    """
    Parse error that causes CLBNodeLimitError along with limit and raise it
    """
    if code != 413:
        return
    match = _CLB_NODE_LIMIT_PATTERN.match(json_body.get("message", ""))
    if match is not None:
        limit = int(match.group(1))
        raise CLBNodeLimitError(lb_id=six.text_type(lb_id), node_limit=limit)


def change_clb_node(lb_id, node_id, condition, weight, _type="PRIMARY"):
    """
    Generate effect to change a node on a load balancer.

    :param str lb_id: The load balancer ID to add the nodes to
    :param str node_id: The node id to change.
    :param str condition: The condition to change to: one of "ENABLED",
        "DRAINING", or "DISABLED"
    :param int weight: The weight to change to.
    :param str _type: The type to change the CLB node to.

    :return: :class:`ServiceRequest` effect

    :raises: :class:`CLBImmutableError`, :class:`CLBDeletedError`,
        :class:`NoSuchCLBError`, :class:`NoSuchCLBNodeError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'PUT',
        append_segments('loadbalancers', lb_id, 'nodes', node_id),
        data={'node': {
            'condition': condition, 'weight': weight, 'type': _type}},
        success_pred=has_code(202))

    @only_json_api_errors
    def _parse_known_errors(code, json_body):
        _process_clb_api_error(code, json_body, lb_id)
        match_errors(
            _expand_clb_matches(
                [(404, _CLB_NO_SUCH_NODE_PATTERN, NoSuchCLBNodeError)],
                lb_id=lb_id, node_id=node_id),
            code,
            json_body)

    return eff.on(error=_parse_known_errors)
    # CLB 202 response here has no body, so no response logging needed


# Number of nodes that can be deleted in `DELETE ../nodes` call as per
# https://developer.rackspace.com/docs/cloud-load-balancers/v1/api-reference/nodes/#bulk-delete-nodes
CLB_BATCH_DELETE_LIMIT = 10


def remove_clb_nodes(lb_id, node_ids):
    """
    Remove multiple nodes from a load balancer.

    :param str lb_id: A load balancer ID.
    :param node_ids: iterable of node IDs.
    :return: Effect of None.

    Succeeds on 202.

    This function will handle the case where *some* of the nodes are valid and
    some aren't, by retrying deleting only the valid ones.
    """
    node_ids = list(node_ids)
    partial = None
    if len(node_ids) > CLB_BATCH_DELETE_LIMIT:
        not_removing = node_ids[CLB_BATCH_DELETE_LIMIT:]
        node_ids = node_ids[:CLB_BATCH_DELETE_LIMIT]
        partial = CLBPartialNodesRemoved(six.text_type(lb_id),
                                         map(six.text_type, not_removing),
                                         map(six.text_type, node_ids))
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'DELETE',
        append_segments('loadbalancers', lb_id, 'nodes'),
        params={'id': map(str, node_ids)},
        success_pred=has_code(202))

    def check_invalid_nodes(exc_info):
        code = exc_info[1].code
        body = exc_info[1].body
        if code == 400:
            message = try_json_with_keys(
                body, ["validationErrors", "messages", 0])
            if message is not None:
                match = _CLB_NODE_REMOVED_PATTERN.match(message)
                if match:
                    removed = concat([group.split(',')
                                      for group in match.groups()])
                    return remove_clb_nodes(lb_id,
                                            set(node_ids) - set(removed))
        six.reraise(*exc_info)

    return eff.on(
        error=catch(APIError, check_invalid_nodes)
    ).on(
        error=only_json_api_errors(
            lambda c, b: _process_clb_api_error(c, b, lb_id))
    ).on(success=lambda _: None if partial is None else raise_(partial))
    # CLB 202 responses here has no body, so no response logging needed.


def get_clb_nodes(lb_id):
    """
    Fetch the nodes of the given load balancer. Returns list of node JSON.
    """
    return service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'GET',
        append_segments('loadbalancers', str(lb_id), 'nodes'),
    ).on(
        error=only_json_api_errors(
            lambda c, b: _process_clb_api_error(c, b, lb_id))
    ).on(
        log_success_response('request-list-clb-nodes', identity)
    ).on(
        success=lambda (response, body): body['nodes'])


def get_clbs():
    """Fetch all LBs for a tenant. Returns list of loadbalancer JSON."""
    return service_request(
        ServiceType.CLOUD_LOAD_BALANCERS, 'GET', 'loadbalancers',
    ).on(
        log_success_response('request-list-clbs', identity)
    ).on(
        success=lambda (response, body): body['loadBalancers'])


def get_clb_node_feed(lb_id, node_id):
    """
    Get the atom feed associated with a CLB node.

    :param int lb_id: Cloud Load balancer ID
    :param int node_id: Node ID of in loadbalancer node

    :returns: Effect of ``list`` of atom entry :class:`Element`
    :rtype: ``Effect``
    """
    return cf.read_entries(
        ServiceType.CLOUD_LOAD_BALANCERS,
        append_segments('loadbalancers', str(lb_id), 'nodes',
                        '{}.atom'.format(node_id)),
        {},
        cf.Direction.NEXT,
        "request-get-clb-node-feed"
    ).on(itemgetter(0)).on(
        error=only_json_api_errors(
            lambda c, b: _process_clb_api_error(c, b, lb_id))
    )


def get_clb_health_monitor(lb_id):
    """
    Return CLB health monitor setting

    :param int lb_id: Loadbalancer ID

    :return: ``Effect`` of ``dict`` representing health monitor config
    """
    return service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'GET',
        append_segments('loadbalancers', str(lb_id), 'healthmonitor')
    ).on(
        error=only_json_api_errors(
            lambda c, b: _process_clb_api_error(c, b, lb_id))
    ).on(
        log_success_response('request-get-clb-healthmon', identity)
    ).on(
        success=lambda (response, body): body["healthMonitor"])
