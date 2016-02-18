"""
Functions to talk to RCv3 service
"""

import re

from otter.cloud_client import (
    ExceptionWithMessage, ServiceType, service_request)
from otter.util.http import append_segments
from otter.util.pure_http import has_code


def _rackconnect_bulk_request(lb_node_pairs, method, success_pred):
    """
    Creates a bulk request for RackConnect v3.0 load balancers.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made or broken.
    :param str method: The method of the request ``"DELETE"`` or
        ``"POST"``.
    :param success_pred: Predicate that determines if a response was
        successful.
    :return: A bulk RackConnect v3.0 request for the given load balancer,
        node pairs.
    :rtype: :class:`Request`
    """
    return service_request(
        ServiceType.RACKCONNECT_V3,
        method,
        append_segments("load_balancer_pools", "nodes"),
        data=[{"cloud_server": {"id": node},
               "load_balancer_pool": {"id": lb}}
              for (lb, node) in lb_node_pairs],
        success_pred=success_pred)


_UUID4_REGEX = ("[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}"
                "-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}")


def _rcv3_re(pattern):
    return re.compile(pattern.format(uuid=_UUID4_REGEX), re.IGNORECASE)


_RCV3_NODE_NOT_A_MEMBER_PATTERN = _rcv3_re(
    "Node (?P<node_id>{uuid}) is not a member of Load Balancer Pool "
    "(?P<lb_id>{uuid})")
_RCV3_NODE_ALREADY_A_MEMBER_PATTERN = _rcv3_re(
    "Cloud Server (?P<node_id>{uuid}) is already a member of Load Balancer "
    "Pool (?P<lb_id>{uuid})")
_RCV3_LB_INACTIVE_PATTERN = _rcv3_re(
    "Load Balancer Pool (?P<lb_id>{uuid}) is not in an ACTIVE state")
_RCV3_LB_DOESNT_EXIST_PATTERN = _rcv3_re(
    "Load Balancer Pool (?P<lb_id>{uuid}) does not exist")


class NodeAlreadyMember(ExceptionWithMessage):
    """
    Node is already a member of RCv3 LB pool
    """
    def __init__(self, lb_id, node_id):
        super(NodeAlreadyMember, self).__init__(
            "Node {node_id} is already member of RCv3 LB {lb_id}".format(
                node_id=node_id, lb_id=lb_id))
        self.lb_id = lb_id
        self.node_id = node_id


class LBInactive(ExceptionWithMessage):
    """
    RCv3 LB pool is not active
    """
    def __init__(self, lb_id):
        super(LBInactive, self).__init__(
            "RCv3 LB {} is not active".format(lb_id))
        self.lb_id = lb_id


class NoSuchLBError(ExceptionWithMessage):
    """
    RCv3 LB pool does not exist
    """
    def __init__(self, lb_id):
        super(NoSuchLBError, self).__init__(
            "RCv3 LB {} does not exist".format(lb_id))
        self.lb_id = lb_id


class BulkErrors(ExceptionWithMessage):
    """
    Raised when RCv3 bulk API errors with multiple reasons
    """
    def __init__(self, exceptions):
        super(BulkErrors, self).__init__(
            "Bulk API errors: {}".format(
                "; ".join(e.message for e in exceptions)))
        self.errors = exceptions


class UnknownBulkResponse(ExceptionWithMessage):
    """
    An unknown response from Bulk API was returned
    """
    def __init__(self, body):
        super(UnknownBulkResponse, self).__init__(
            "Unknown bulk API response: {}".format(body))


def bulk_add(lb_node_pairs):
    """
    Bulk add LB Nodes

    :param list lb_node_pairs: List of (lb_id, node_id) tuples
    :return: Effect of None when succeeds otherwise raises above exceptions
    """
    eff = _rackconnect_bulk_request(lb_node_pairs, "POST",
                                    success_pred=has_code(201, 409))
    return eff.on(_check_bulk_add(lb_node_pairs))


@curry
def _check_bulk_add(attempted_pairs, result):
    """
    Checks if the RCv3 bulk add command was successful.
    """
    response, body = result

    if response.code == 201:  # All done!
        return

    errors = []
    to_retry = attempted_pairs
    for error in body["errors"]:
        match = _RCV3_NODE_ALREADY_A_MEMBER_PATTERN.match(error)
        if match is not None:
            pair = match.groupdict()
            errors.append(NodeAlreadyMember(pair["lb_id"], pair["node_id"]))

        match = _RCV3_LB_INACTIVE_PATTERN.match(error)
        if match is not None:
            errors.append(LBInactive(match.groupdict()["lb_id"]))

        match = _RCV3_LB_DOESNT_EXIST_PATTERN.match(error)
        if match is not None:
            errors.append(NoSuchLBError(match.groupdict()["lb_id"]))

    if errors:
        raise BulkErrors(errors)
    else:
        raise UnknownBulkResponse(body)
