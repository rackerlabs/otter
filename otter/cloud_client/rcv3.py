"""
Functions to talk to RCv3 service
"""

import json
import re

from pyrsistent import pset

from toolz.functoolz import curry, identity

from otter.cloud_client import (
    ExceptionWithMessage, ServiceType, log_success_response, service_request)
from otter.util.http import append_segments
from otter.util.pure_http import has_code


def _sorted_data(lb_node_pairs):
    """
    Return HTTP request body to be sent to RCv3 load_balancer_pools/nodes API
    from list of (lb_id, node_id) tuples. The returned list is sorted to allow
    easier testing with predictability.

    :param list lb_node_pairs: List of (lb_id, node_id) tuples
    :return: List of ``dict``
    """
    return sorted(
        [{"cloud_server": {"id": node}, "load_balancer_pool": {"id": lb}}
         for (lb, node) in lb_node_pairs],
        key=lambda e: (e["load_balancer_pool"]["id"], e["cloud_server"]["id"]))


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
    req_body = _sorted_data(lb_node_pairs)  # predictability for testing
    return service_request(
        ServiceType.RACKCONNECT_V3,
        method,
        append_segments("load_balancer_pools", "nodes"),
        data=req_body,
        success_pred=success_pred).on(
            log_success_response("request-rcv3-bulk", identity,
                                 request_body=json.dumps(req_body)))


def _re(pattern):
    return re.compile(pattern, re.IGNORECASE)


_SERVER_NOT_A_MEMBER_PATTERN = _re(
    "Cloud Server (?P<server_id>.*) is not a member of Load Balancer Pool "
    "(?P<lb_id>.*)")
_NODE_ALREADY_A_MEMBER_PATTERN = _re(
    "Cloud Server (?P<node_id>.*) is already a member of Load Balancer "
    "Pool (?P<lb_id>.*)")
_LB_INACTIVE_PATTERN = _re(
    "Load Balancer Pool (?P<lb_id>.*) is not in an ACTIVE state")
_LB_DOESNT_EXIST_PATTERN = _re(
    "Load Balancer Pool (?P<lb_id>.*) does not exist")
_SERVER_UNPROCESSABLE = _re(
    "Cloud Server (?P<server_id>.*) is unprocessable")
_SERVER_DOES_NOT_EXIST = _re(
    "Cloud Server (?P<server_id>.*) does not exist")


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


class NoSuchServerError(ExceptionWithMessage):
    """
    Cloud server does not exist
    """
    def __init__(self, server_id):
        super(NoSuchServerError, self).__init__(
            "Cloud server {} does not exist".format(server_id))
        self.server_id = server_id


class BulkErrors(ExceptionWithMessage):
    """
    Raised when RCv3 bulk API errors with multiple reasons
    """
    def __init__(self, exceptions):
        super(BulkErrors, self).__init__(
            "Bulk API errors: {}".format(
                "; ".join(e.message for e in exceptions)))
        self.errors = pset(exceptions)


class UnknownBulkResponse(ExceptionWithMessage):
    """
    An unknown response from Bulk API was returned
    """
    def __init__(self, body):
        super(UnknownBulkResponse, self).__init__(
            "Unknown bulk API response: {}".format(body))


def normalize_lb_id(lb_id):
    """
    Load balancer IDs are case insensitive. Here, we normalize it to lower case
    for consistency and comparison
    """
    return lb_id.lower()


def bulk_add(lb_node_pairs):
    """
    Bulk add RCv3 LB Nodes. If RCv3 returns error about a pair being already
    a member, it retries the remaining pairs *provided* there are no other
    errors

    :param list lb_node_pairs: List of (lb_id, node_id) tuples
    :return: Effect of response body ``dict`` when succeeds with 201 or None
        when all pairs are already members. Otherwise raises `BulkErrors` or
        `UnknownBulkResponse`
    """
    pairs = [(normalize_lb_id(l), n) for l, n in lb_node_pairs]
    eff = _rackconnect_bulk_request(pairs, "POST",
                                    success_pred=has_code(201, 409))
    return eff.on(_check_bulk_add(pairs))


@curry
def _check_bulk_add(attempted_pairs, result):
    """
    Checks if the RCv3 bulk add command was successful.
    """
    response, body = result

    if response.code == 201:  # All done!
        return body

    errors = []
    exists = pset()
    for error in body["errors"]:
        match = _NODE_ALREADY_A_MEMBER_PATTERN.match(error)
        if match is not None:
            pair = match.groupdict()
            exists = exists.add(
                (normalize_lb_id(pair["lb_id"]), pair["node_id"]))
            continue

        match = _LB_INACTIVE_PATTERN.match(error)
        if match is not None:
            errors.append(LBInactive(match.group("lb_id")))
            continue

        match = _LB_DOESNT_EXIST_PATTERN.match(error)
        if match is not None:
            errors.append(NoSuchLBError(match.group("lb_id")))
            continue

        match = _SERVER_UNPROCESSABLE.match(error)
        if match is not None:
            errors.append(ServerUnprocessableError(match.group("server_id")))
        else:
            raise UnknownBulkResponse(body)

    if errors:
        raise BulkErrors(errors)
    elif exists:
        to_retry = pset(attempted_pairs) - exists
        return bulk_add(to_retry) if to_retry else None
    else:
        raise UnknownBulkResponse(body)


def bulk_delete(lb_node_pairs):
    """
    Bulk delete RCv3 LB Nodes. If RCv3 returns error about a pair not being
    a member or server or lb not existing it retries the remaining pairs
    *provided* there are no LBInactive errors. Otherwise `BulkErrors` with
    `LBInactive` errors in it is raised

    TODO: Ideally its outside the scope of this function to decide whether
    to retry on LB and Server does not exist error. There should be a parameter
    for this: lb_deleted_ok, server_deleted_ok?

    :param list lb_node_pairs: List of (lb_id, node_id) tuples
    :return: Effect of response body dict when succeeds or Effect of None if
        all nodes are already deleted. Otherwise raises `BulkErrors` or
        `UnknownBulkResponse`
    """
    pairs = [(normalize_lb_id(l), n) for l, n in lb_node_pairs]
    eff = _rackconnect_bulk_request(pairs, "DELETE",
                                    success_pred=has_code(204, 409))
    return eff.on(_check_bulk_delete(pairs))


@curry
def _check_bulk_delete(attempted_pairs, result):
    """
    Checks if the RCv3 bulk delete command was successful.
    """
    response, body = result

    if response.code == 204:  # All done!
        return body

    errors = []
    non_members = pset()
    for error in body["errors"]:
        match = _SERVER_NOT_A_MEMBER_PATTERN.match(error)
        if match is not None:
            pair = match.groupdict()
            non_members = non_members.add(
                (normalize_lb_id(pair["lb_id"]), pair["server_id"]))
            continue

        match = _LB_INACTIVE_PATTERN.match(error)
        if match is not None:
            errors.append(LBInactive(match.group("lb_id")))
            continue

        match = _LB_DOESNT_EXIST_PATTERN.match(error)
        if match is not None:
            del_lb_id = normalize_lb_id(match.group("lb_id"))
            # consider all pairs with this LB to be removed
            removed = [(lb_id, node_id) for lb_id, node_id in attempted_pairs
                       if lb_id == del_lb_id]
            non_members |= pset(removed)
            continue

        match = _SERVER_DOES_NOT_EXIST.match(error)
        if match is not None:
            del_server_id = match.group("server_id")
            # consider all pairs with this server to be removed
            removed = [(lb_id, node_id) for lb_id, node_id in attempted_pairs
                       if node_id == del_server_id]
            non_members |= pset(removed)
        else:
            raise UnknownBulkResponse(body)

    if errors:
        raise BulkErrors(errors)
    elif non_members:
        to_retry = pset(attempted_pairs) - non_members
        return bulk_delete(to_retry) if to_retry else None
    else:
        raise UnknownBulkResponse(body)
