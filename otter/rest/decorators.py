"""
Wrapper for handling faults in a scalable fashion
"""

from functools import wraps
import json

from jsonschema import ValidationError

from twisted.internet import defer
from twisted.python import reflect
from otter.util.hashkey import generate_transaction_id
from otter.util.deferredutils import unwrap_first_error
from otter.log import log

from otter.json_schema import validate


def fails_with(mapping):
    """
    Map a result.  In success case, returns the success_code, otherwise uses
    the mapping to determine the correct error code to return.  Failing to
    find a mapping, returns 500.
    """
    def decorator(f):
        @wraps(f)
        def _(request, bound_log, *args, **kwargs):

            def _fail(failure, request):
                failure = unwrap_first_error(failure)
                code = 500
                if failure.type in mapping:
                    code = mapping[failure.type]
                    errorObj = {
                        'type': failure.type.__name__,
                        'code': code,
                        'message': failure.value.message,
                        'details': getattr(failure.value, 'details', '')
                    }
                    bound_log.bind(
                        uri=request.uri,
                        **errorObj
                    ).msg(failure.value.message)
                else:
                    errorObj = {
                        'type': 'InternalError',
                        'code': code,
                        'message': 'An Internal Error was encountered',
                        'details': ''
                    }
                    bound_log.bind(
                        uri=request.uri,
                        code=code
                    ).err(failure, 'Unhandled Error handling request')
                request.setResponseCode(code)
                return json.dumps(errorObj)

            d = defer.maybeDeferred(f, request, bound_log, *args, **kwargs)
            d.addErrback(_fail, request)
            return d
        return _
    return decorator


def select_dict(subset, superset):
    """
    Selects a subset of entries from the superset
    :return: the subset as a dict
    """
    res = {}
    for key in subset:
        if key in superset:
            res[key] = superset[key]
    return res


def succeeds_with(success_code):
    """
    Map a result.  In success case, returns the success_code, otherwise uses
    the mapping to determine the correct error code to return.  Failing to
    find a mapping, returns 500.
    """
    def decorator(f):
        @wraps(f)
        def _(request, bound_log, *args, **kwargs):
            def _succeed(result, request):
                # Default twisted response code is 200.  Assuming that if this
                # is 200, then it is the default and can be overriden
                if request.code == 200:
                    request.setResponseCode(success_code)
                bound_log.bind(
                    uri=request.uri,
                    code=request.code
                ).msg('Request succeeded')
                return result

            d = defer.maybeDeferred(f, request, bound_log, *args, **kwargs)
            d.addCallback(_succeed, request)
            return d
        return _
    return decorator


def bind_log(f):
    """
    Binds keyword arguments to log
    """
    @wraps(f)
    def _(request, log, *args, **kwargs):
        bound_log = log.bind(**kwargs)
        return f(request, bound_log, *args, **kwargs)
    return _


def with_transaction_id():
    """
    Generates a request txnid
    """
    def decorator(f):
        @wraps(f)
        def _(request, *args, **kwargs):
            transaction_id = generate_transaction_id()
            request.setHeader('X-Response-Id', transaction_id)
            bound_log = log.bind(
                system=reflect.fullyQualifiedName(f),
                transaction_id=transaction_id)
            bound_log.bind(
                method=request.method,
                uri=request.uri,
                clientproto=request.clientproto,
                referer=request.getHeader("referer"),
                useragent=request.getHeader("user-agent")
            ).msg("Received request")
            return bind_log(f)(request, bound_log, *args, **kwargs)
        return _
    return decorator


class InvalidJsonError(Exception):
    """Null"""
    pass


def validate_body(schema):
    """
    Decorator that validates dependent on the schema passed in.
    See http://json-schema.org/ for schema documentation.

    :return: decorator
    """
    def decorator(f):
        @wraps(f)
        def _(request, *args, **kwargs):
            try:
                request.content.seek(0)
                data = json.loads(request.content.read())
                validate(data, schema)
            except ValueError as e:
                return defer.fail(InvalidJsonError())
            except ValidationError, e:
                return defer.fail(e)
            kwargs['data'] = data
            return f(request, *args, **kwargs)

        return _
    return decorator
