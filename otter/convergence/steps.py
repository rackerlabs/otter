"""Steps for convergence."""
import json
import re

from functools import partial

from characteristic import attributes

from effect import Effect, Func

from pyrsistent import pset, thaw

from toolz.dicttoolz import get_in
from toolz.itertoolz import concat

from zope.interface import Interface, implementer

from otter.constants import ServiceType
from otter.convergence.model import StepResult
from otter.http import has_code, service_request
from otter.util.fp import predicate_any
from otter.util.hashkey import generate_server_name
from otter.util.http import APIError, append_segments


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_effect():
        """Return an Effect which performs this step."""


def set_server_name(server_config_args, name_suffix):
    """
    Append the given name_suffix to the name of the server in the server
    config.

    :param server_config_args: The server configuration args.
    :param name_suffix: the suffix to append to the server name. If no name was
        specified, it will be used as the name.
    """
    name = server_config_args['server'].get('name')
    if name is not None:
        name = '{0}-{1}'.format(name, name_suffix)
    else:
        name = name_suffix
    return server_config_args.set_in(('server', 'name'), name)


def _try_json_message(maybe_json_error, keys):
    """
    Attemp to grab the message body from possibly a JSON error body.  If
    invalid JSON, or if the JSON is of an unexpected format (keys are not
    found), `None` is returned.
    """
    try:
        error_body = json.loads(maybe_json_error)
    except (ValueError, TypeError):
        return None
    else:
        return get_in(keys, error_body, None)


def _forbidden_plaintext(message):
    return re.compile(
        "^403 Forbidden\n\nAccess was denied to this resource\.\n\n ({0})$"
        .format(message))

_NOVA_403_NO_PUBLIC_NETWORK = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000\) not allowed")
_NOVA_403_PUBLIC_SERVICENET_BOTH_REQUIRED = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000,"
    "11111111-1111-1111-1111-111111111111\) required but missing")
_NOVA_403_RACKCONNECT_NETWORK_REQUIRED = _forbidden_plaintext(
    "Exactly 1 isolated network\(s\) must be attached")


def _parse_nova_user_error(api_error):
    """
    Parse API errors for user failures on creating a server.

    :param api_error: The error returned from Nova
    :type api_error: :class:`APIError`

    :return: the nova message as to why the creation failed, if it was a user
        failure.  None otherwise.
    :rtype: `str` or `None`
    """
    if api_error.code == 400:
        message = _try_json_message(api_error.body,
                                    ("badRequest", "message"))
        if message:
            return message

    elif api_error.code == 403:
        message = _try_json_message(api_error.body,
                                    ("forbidden", "message"))
        if message:
            return message

        for pat in (_NOVA_403_RACKCONNECT_NETWORK_REQUIRED,
                    _NOVA_403_NO_PUBLIC_NETWORK,
                    _NOVA_403_PUBLIC_SERVICENET_BOTH_REQUIRED):
            m = pat.match(api_error.body)
            if m:
                return m.groups()[0]


@implementer(IStep)
@attributes(['server_config'])
class CreateServer(object):
    """
    A server must be created.

    :ivar pmap server_config: Nova launch configuration.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to create a server."""
        eff = Effect(Func(generate_server_name))

        def got_name(random_name):
            server_config = set_server_name(self.server_config, random_name)
            return service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data=thaw(server_config),
                success_pred=has_code(202),
                reauth_codes=(401,))

        def report_success(result):
            return StepResult.SUCCESS, []

        def report_failure(result):
            """
            If the failure is an APIError with a 400 or 403, attempt to parse
            the results and return a :obj:`StepResult.FAILURE` - if the errors
            are unrecognized, return a :obj:`StepResult.RETRY` for now.
            """
            err_type, error, traceback = result
            if err_type == APIError:
                message = _parse_nova_user_error(error)
                if message is not None:
                    return StepResult.FAILURE, [message]

            return StepResult.RETRY, []

        return eff.on(got_name).on(success=report_success,
                                   error=report_failure)


@implementer(IStep)
@attributes(['server_id'])
class DeleteServer(object):
    """
    A server must be deleted.

    :ivar str server_id: a Nova server ID.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to delete a server."""
        eff = service_request(
            ServiceType.CLOUD_SERVERS,
            'DELETE',
            append_segments('servers', self.server_id),
            success_pred=has_code(204, 404))

        def report_success(result):
            return StepResult.SUCCESS, []

        def report_failure(result):
            return StepResult.RETRY, []

        return eff.on(success=report_success, error=report_failure)


@implementer(IStep)
@attributes(['server_id', 'key', 'value'])
class SetMetadataItemOnServer(object):
    """
    A metadata key/value item must be set on a server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)
    """
    def as_effect(self):
        """Produce a :obj:`Effect` to set a metadata item on a server"""
        return service_request(
            ServiceType.CLOUD_SERVERS,
            'PUT',
            append_segments('servers', self.server_id, 'metadata', self.key),
            data={'meta': {self.key: self.value}})


_CLB_DUPLICATE_NODES_PATTERN = re.compile(
    "^Duplicate nodes detected. One or more nodes already configured "
    "on load balancer.$")
_CLB_PENDING_UPDATE_PATTERN = re.compile(
    "^Load Balancer '\d+' has a status of 'PENDING_UPDATE' and is considered "
    "immutable.$")
_CLB_DELETED_PATTERN = re.compile(
    "^(Load Balancer '\d+' has a status of 'PENDING_DELETE' and is|"
    "The load balancer is deleted and) considered immutable.$")
_CLB_NODE_REMOVED_PATTERN = re.compile(
    "^Node ids ((?:\d+,)*(?:\d+)) are not a part of your loadbalancer\s*$")


def _check_clb_422(*regex_matches):
    """
    A success predicate that succeeds if the status code is 422 and the content
    matches the regex.  Used for detecting duplicate nodes on add to CLB, and
    the load balancer being deleted or pending delete on remove from CLB.

    It's unfortunate this involves parsing the body.
    """
    def check_response(response, content):
        """
        Check that the given response has a 422 code and its body matches the
        regex.

        Expects the content to be JSON, so whatever uses this should make sure
        that the service request is called with ``json_response=True``,
        which it should be by default.
        """
        if response.code == 422:
            message = content.get('message', '')
            return any([regex.search(message) for regex in regex_matches])
        return False

    return check_response


@implementer(IStep)
@attributes(['lb_id', 'address_configs'])
class AddNodesToCLB(object):
    """
    Multiple nodes must be added to a load balancer.

    Note: This is not correctly documented in the load balancer documentation -
    it is documented as "Add Node" (singular), but the examples show multiple
    nodes being added.

    :ivar str lb_id: The cloud load balancer ID to add nodes to.
    :ivar iterable address_configs: A collection of two-tuples of address and
        :obj:`CLBDescription`.

    Succeed unconditionally on 202 and 413 (over limit, so try again later).

    Succeed conditionally on 422 if duplicate nodes are detected - the
    duplicate codes are not enumerated, so just try again the next convergence
    cycle.

    Succeed conditionally on 422 if the load balancer is in PENDING_UPDATE
    state, which happens because CLB locks for a few seconds and cannot be
    changed again after an update - can be fixed next convergence cycle.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to add nodes to CLB"""
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            append_segments('loadbalancers', str(self.lb_id), "nodes"),
            data={'nodes': [{'address': address, 'port': lbc.port,
                             'condition': lbc.condition.name,
                             'weight': lbc.weight,
                             'type': lbc.type.name}
                            for address, lbc in self.address_configs]},
            success_pred=predicate_any(
                has_code(202, 413),
                _check_clb_422(_CLB_DUPLICATE_NODES_PATTERN,
                               _CLB_PENDING_UPDATE_PATTERN)))


@implementer(IStep)
@attributes(['lb_id', 'node_ids'])
class RemoveNodesFromCLB(object):
    """
    One or more IPs must be removed from a load balancer.

    :ivar str lb_id: The cloud load balancer ID to remove nodes from.
    :ivar iterable node_ids: A collection of node IDs to remove from the CLB.

    Succeed unconditionally on 202 and 413 (over limit, so try again later).

    Succeed conditionally on 422 if the load balancer is in PENDING_UPDATE
    state, which happens because CLB locks for a few seconds and cannot be
    changed again after an update - can be fixed next convergence cycle.

    Succeed conditionally on 422 if the load balancer is in PENDING_DELETE
    state, or already deleted, which means we don't have to remove any nodes.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to remove a load balancer node."""
        eff = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            append_segments('loadbalancers', str(self.lb_id), 'nodes'),
            params={'id': [str(node_id) for node_id in self.node_ids]},
            success_pred=predicate_any(
                has_code(202, 413, 400),
                _check_clb_422(_CLB_PENDING_UPDATE_PATTERN,
                               _CLB_DELETED_PATTERN)))
        # 400 means that there are some nodes that are no longer on the
        # load balancer.  Parse them out and try again.
        return eff.on(partial(
            _clb_check_bulk_delete, self.lb_id, self.node_ids))


def _clb_check_bulk_delete(lb_id, attempted_nodes, result):
    """
    Check if the CLB bulk deletion command failed with a 400, and if so,
    returns the next step to try and remove the remaining nodes. This is
    necessary because CLB bulk deletes are atomic-ish.

    This seems to be the only case in which this API endpoint returns a 400.

    All other cases are considered unambiguous successes.

    :param result: The result of the :class:`ServiceRequest`. This should be a
        2-tuple of the response object and the (parsed) body.
    :ivar str lb_id: The cloud load balancer ID to remove nodes from.
    :param attempted_nodes: The node IDs that were attempted to be
        removed. This is the :attr:`node_ids` attribute of
        :class:`RemoveNodesFromCLB` instances.

    This assumes that the result body is already parsed into JSON.
    """
    response, body = result
    if response.code == 400:
        message = get_in(["validationErrors", "messages", 0], body)
        match = _CLB_NODE_REMOVED_PATTERN.match(message)
        if match:
            removed = concat([group.split(',') for group in match.groups()])
            retry = RemoveNodesFromCLB(
                lb_id=lb_id, node_ids=pset(attempted_nodes) - pset(removed))
            return retry.as_effect()


@implementer(IStep)
@attributes(['lb_id', 'node_id', 'condition', 'weight', 'type'])
class ChangeCLBNode(object):
    """
    An existing port mapping on a load balancer must have its condition,
    weight, or type modified.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to modify a load balancer node."""
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            append_segments('loadbalancers', self.lb_id,
                            'nodes', self.node_id),
            data={'condition': self.condition,
                  'weight': self.weight},
            success_pred=has_code(202))


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


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkAddToRCv3(object):
    """
    Some connections must be made between some combination of servers
    and RackConnect v3.0 load balancers.

    Each connection is independently specified.

    See http://docs.rcv3.apiary.io/#post-%2Fv3%2F{tenant_id}
    %2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made.
    """
    def _bare_effect(self):
        """
        Just the RCv3 bulk request effect, with no callbacks.
        """
        return _rackconnect_bulk_request(self.lb_node_pairs, "POST",
                                         success_pred=has_code(201, 409))

    def as_effect(self):
        """
        Produce a :obj:`Effect` to add some nodes to some RCv3 load
        balancers.
        """
        eff = self._bare_effect()
        return eff.on(partial(_rcv3_check_bulk_add, self.lb_node_pairs))


def _rcv3_check_bulk_add(attempted_pairs, result):
    """
    Checks if the RCv3 bulk add command was successful.
    """
    response, body = result

    if response.code == 201:  # All done!
        return StepResult.SUCCESS, []

    failure_reasons = []
    to_retry = pset(attempted_pairs)
    for error in body["errors"]:
        match = _RCV3_NODE_ALREADY_A_MEMBER_PATTERN.match(error)
        if match is not None:
            to_retry -= pset([match.groups()[::-1]])

        match = _RCV3_LB_INACTIVE_PATTERN.match(error)
        if match is not None:
            failure_reasons.append(
                "RCv3 LB {lb_id} was inactive".format(**match.groupdict()))

        match = _RCV3_LB_DOESNT_EXIST_PATTERN.match(error)
        if match is not None:
            failure_reasons.append(
                "RCv3 LB {lb_id} does not exist".format(**match.groupdict()))

    if failure_reasons:
        return StepResult.FAILURE, failure_reasons
    elif to_retry:
        next_step = BulkAddToRCv3(lb_node_pairs=to_retry)
        return next_step.as_effect()
    else:
        return StepResult.SUCCESS, []


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkRemoveFromRCv3(object):
    """
    Some connections must be removed between some combination of nodes
    and RackConnect v3.0 load balancers.

    See http://docs.rcv3.apiary.io/#delete-%2Fv3%2F{tenant_id}
    %2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be removed.
    """
    def _bare_effect(self):
        """
        Just the RCv3 bulk request effect, with no callbacks.
        """
        # While 409 isn't success, that has to be introspected by
        # _rcv3_check_bulk_delete in order to recover from it.
        return _rackconnect_bulk_request(self.lb_node_pairs, "DELETE",
                                         success_pred=has_code(204, 409))

    def as_effect(self):
        """
        Produce a :obj:`Effect` to remove some nodes from some RCv3 load
        balancers.
        """
        eff = self._bare_effect()
        return eff.on(partial(_rcv3_check_bulk_delete, self.lb_node_pairs))


def _rcv3_check_bulk_delete(attempted_pairs, result):
    """Checks if the RCv3 bulk deletion command was successful.

    The request is considered successful if the response code indicated
    unambiguous success, or the nodes we're trying to remove aren't on the
    respective load balancers we're trying to remove them from, or if the load
    balancers we're trying to remove from aren't active.

    If a node wasn't on the load balancer we tried to remove it from, or a
    load balancer we were supposed to remove things from wasn't active,
    returns the next step to try and remove the remaining pairs. This is
    necessary because RCv3 bulk requests are atomic-ish.

    :param attempted_pairs: The (lb, node) pairs that were attempted to be
        removed. This is the :attr:`lb_node_pairs` attribute of
        :class:`BulkRemoveFromRCv3` instances.
    :param result: The result of the :class:`ServiceRequest`. This should be a
        2-tuple of the response object and the (parsed) body.
    """
    response, body = result

    if response.code == 204:  # All done!
        return StepResult.SUCCESS, []

    to_retry = pset(attempted_pairs)
    for error in body["errors"]:
        match = _RCV3_NODE_NOT_A_MEMBER_PATTERN.match(error)
        if match is not None:
            to_retry -= pset([match.groups()[::-1]])

        match = (_RCV3_LB_INACTIVE_PATTERN.match(error)
                 or _RCV3_LB_DOESNT_EXIST_PATTERN.match(error))
        if match is not None:
            bad_lb_id, = match.groups()
            to_retry = pset([(lb_id, node_id)
                             for (lb_id, node_id) in to_retry
                             if lb_id != bad_lb_id])

    if to_retry:
        next_step = BulkRemoveFromRCv3(lb_node_pairs=to_retry)
        return next_step.as_effect()
    else:
        return StepResult.SUCCESS, []
