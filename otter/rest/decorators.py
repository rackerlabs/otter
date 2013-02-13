"""
Wrapper for handling faults in a scalable fashion
"""

from functools import wraps
import json

import jsonschema

from twisted.internet import defer
from otter.util.hashkey import generate_txnid
from otter.log import log


def _get_real_failure(possible_first_error):
    """
    Failures returned by :method:`defer.gatherResults` are failures that wrap
    a defer.FirstError, which wraps the inner failure.

    Checks failure to see if it is a defer.FirstError.  If it is, recursively
    gets the underlying failure that it wraps (in case it is a first error
    wrapping a first error, etc.)

    :param possible_first_error: a failure that may wrap a
        :class:`defer.FirstError`
    :type possible_first_error: :class:`Failure`

    :return: :class:`Failure` that is under any/all the
        :class:`defer.FirstError`s
    """
    if possible_first_error.check(defer.FirstError):
        return _get_real_failure(possible_first_error.value.subFailure)
    return possible_first_error  # not a defer.FirstError


def fails_with(mapping):
    """
    Map a result.  In success case, returns the success_code, otherwise uses
    the mapping to determine the correct error code to return.  Failing to
    find a mapping, returns 500.
    """
    def decorator(f):
        @wraps(f)
        def _(request, *args, **kwargs):

            def _fail(failure, request):
                failure = _get_real_failure(failure)
                code = 500
                if failure.type in mapping:
                    code = mapping[failure.type]
                    errorObj = {
                        'type': failure.type.__name__,
                        'code': code,
                        'message': failure.value.message,
                        'details': getattr(failure.value, 'details', '')
                    }
                else:
                    errorObj = {
                        'type': 'InternalError',
                        'code': code,
                        'message': 'An Internal Error was encountered',
                        'details': ''
                    }
                request.setResponseCode(code)
                log.failure(failure).error('fails_with internal error')
                return json.dumps(errorObj)

            d = defer.maybeDeferred(f, request, *args, **kwargs)
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
        def _(request, *args, **kwargs):
            def _succeed(result, request):
                if request.code is None:
                    request.setResponseCode(success_code)
                return result

            d = defer.maybeDeferred(f, request, *args, **kwargs)
            d.addCallback(_succeed, request)
            return d
        return _
    return decorator


def has_request_txnid():
    """
    Generates a request txnid
    """
    def decorator(f):
        @wraps(f)
        def _(request, *args, **kwargs):
            txnId = generate_txnid()
            request.setHeader('X-Response-Id', txnId)
            return f(request, txnId, *args, **kwargs)
        return _
    return decorator


def has_txnid_bound_log():
    """
    Generates a bound log containing the txnid
    """
    def decorator(f):
        @wraps(f)
        def _(request, txnId, *args, **kwargs):
            bound_log = log.fields(txnId=txnId)
            return f(request, bound_log, *args, **kwargs)
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
                jsonschema.validate(data, schema)
            except ValueError as e:
                return defer.fail(InvalidJsonError())
            except jsonschema.ValidationError, e:
                return defer.fail(e)
            kwargs['data'] = data
            return f(request, *args, **kwargs)

        return _
    return decorator
