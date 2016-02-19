"""
Functions to talk to RCv3 service
"""

import json
import re

from pyrsistent import pset

from toolz.functoolz import curry, identity

from otter.cloud_client import (
    ExceptionWithMessage, ServiceType, service_request, log_success_response)
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
    req_body = [{"cloud_server": {"id": node},
                 "load_balancer_pool": {"id": lb}}
                for (lb, node) in lb_node_pairs]
    return service_request(
        ServiceType.RACKCONNECT_V3,
        method,
        append_segments("load_balancer_pools", "nodes"),
        data=req_body,
        success_pred=success_pred).on(
            log_success_response("rcv3-bulk-request", identity,
                                 request_body=json.dumps(req_body)))


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
_RCV3_SERVER_UNPROCESSABLE = _rcv3_re(
    "Cloud Server (?P<server_id>{uuid}) is unprocessable")


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


class ServerUnprocessableError(ExceptionWithMessage):
    """
    Cloud server attempting to attach to RCv3 LB pool is not processable
    """
    def __init__(self, server_id):
        fmt = "Cloud server {} cannot be accessed when adding to RCv3 LB"
        super(ServerUnprocessableError, self).__init__(fmt.format(server_id))
        self.server_id = server_id


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
    Bulk add RCv3 LB Nodes. If RCv3 returns error about a pair being already
    a member, it retries the remaining pairs *provided* there are no other
    errors

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
    exists = pset()
    for error in body["errors"]:
        match = _RCV3_NODE_ALREADY_A_MEMBER_PATTERN.match(error)
        if match is not None:
            pair = match.groupdict()
            exists = exists.append((pair["lb_id"], pair["node_id"]))

        match = _RCV3_LB_INACTIVE_PATTERN.match(error)
        if match is not None:
            errors.append(LBInactive(match.group("lb_id")))

        match = _RCV3_LB_DOESNT_EXIST_PATTERN.match(error)
        if match is not None:
            errors.append(NoSuchLBError(match.group("lb_id")))

        match = _RCV3_SERVER_UNPROCESSABLE.match(error)
        if match is not None:
            errors.append(ServerUnprocessableError(match.group("server_id")))

    if errors:
        raise BulkErrors(errors)
    elif exists:
        return bulk_add(pset(attempted_pairs) - exists)
    else:
        raise UnknownBulkResponse(body)
