import traceback

from toolz.functoolz import identity

from singledispatch import singledispatch

from sumtypes import match

from otter.cloud_client import CLBDeletedError, NoSuchCLBError
from otter.convergence.model import ErrorReason
from otter.log.formatters import serialize_to_jsonable

def present_reasons(reasons):
    """
    Get a list of user-presentable messages from a list of :obj:`ErrorReason`.
    """
    @match(ErrorReason)
    class _present_reason(object):
        def Exception(exc_info): return _present_exception(exc_info[1])
        def _(_): return None
    return filter(None, map(_present_reason, reasons))


@singledispatch
def _present_exception(exception):
    """Get a user-presentable message or None from an exception instance."""
    return None


@_present_exception.register(NoSuchCLBError)
def _present_no_such_clb_error(exception):
    return "Cloud Load Balancer does not exist: %s" % (exception.lb_id,)


@_present_exception.register(CLBDeletedError)
def _present_clb_deleted_error(exception):
    return ("Cloud Load Balancer is currently being deleted: %s"
            % (exception.lb_id,))


@match(ErrorReason)
class structure_reason(object):
    def Exception(exc_info):
        return  {
            'exception': serialize_to_jsonable(exc_info[1]),
            'traceback': ''.join(traceback.format_exception(*exc_info))}
    _ = identity
