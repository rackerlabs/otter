import traceback

from singledispatch import singledispatch

from sumtypes import match

from toolz.functoolz import identity

from otter.cloud_client import (
    CLBDeletedError,
    CLBNodeLimitError,
    CreateServerConfigurationError,
    CreateServerOverQuoteError,
    NoSuchCLBError,
    NoSuchCLBNodeError
)
from otter.convergence.model import ErrorReason
from otter.log.formatters import serialize_to_jsonable


def present_reasons(reasons):
    """
    Get a list of user-presentable messages from a list of :obj:`ErrorReason`.
    """
    @match(ErrorReason)
    class _present_reason(object):
        def Exception(exc_info):
            return _present_exception(exc_info[1])

        def UserMessage(message):
            return message

        def _(_):
            return None

    return filter(None, map(_present_reason, reasons))


@singledispatch
def _present_exception(exception):
    """Get a user-presentable message or None from an exception instance."""
    return None


@_present_exception.register(NoSuchCLBError)
def _present_no_such_clb_error(exception):
    return "Cloud Load Balancer does not exist: {0}".format(exception.lb_id)


@_present_exception.register(CLBDeletedError)
def _present_clb_deleted_error(exception):
    return "Cloud Load Balancer is currently being deleted: {0}".format(
        exception.lb_id)


@_present_exception.register(NoSuchCLBNodeError)
def _present_no_clb_node_error(exception):
    return "Node {} of Cloud Load Balancer {} does not exist".format(
        exception.node_id, exception.lb_id)


@_present_exception.register(CLBNodeLimitError)
def _present_clb_node_limit_error(exception):
    return "Cannot create more than {} nodes in Cloud Load Balancer {}".format(
        exception.node_limit, exception.lb_id)


@_present_exception.register(CreateServerConfigurationError)
def _present_server_configuration_error(exception):
    return "Server launch configuration is invalid: {0}".format(
        exception.message)


@_present_exception.register(CreateServerOverQuoteError)
def _present_server_over_limit_error(exception):
    return "Servers cannot be created: {0}".format(exception.message)


@match(ErrorReason)
class structure_reason(object):
    """
    Get a structured representation of an ErrorReason, suitable for logging
    with a structured logger.

    :return: dict
    """
    def Exception(exc_info):
        return {
            'exception': serialize_to_jsonable(exc_info[1]),
            'traceback': ''.join(traceback.format_exception(*exc_info))}

    def String(string):
        # So that the "reasons" are all the same structure, so that it can be
        # mapped if using elasticsearch
        return {'string': string}

    Structured = identity

    def UserMessage(message):
        return {'user-message': message}
