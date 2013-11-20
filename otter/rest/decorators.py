"""
Wrapper for handling faults in a scalable fashion
"""

from functools import wraps
import json

from jsonschema import ValidationError

from twisted.internet import defer
from twisted.python import reflect

from otter.log import audit
from otter.util.config import config_value
from otter.util.hashkey import generate_transaction_id
from otter.util.deferredutils import unwrap_first_error

from otter.json_schema import validate


def fails_with(mapping):
    """
    Map a result.  In success case, returns the success_code, otherwise uses
    the mapping to determine the correct error code to return.  Failing to
    find a mapping, returns 500.
    """
    def decorator(f):
        @wraps(f)
        def _(self, request, *args, **kwargs):

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
                    self.log.bind(
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
                    self.log.bind(
                        uri=request.uri,
                        code=code
                    ).err(failure, 'Unhandled Error handling request')
                request.setResponseCode(code)
                return json.dumps({'error': errorObj})

            d = defer.maybeDeferred(f, self, request, *args, **kwargs)
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
        def _(self, request, *args, **kwargs):
            def _succeed(result, request):
                # Default twisted response code is 200.  Assuming that if this
                # is 200, then it is the default and can be overriden
                if request.code == 200:
                    request.setResponseCode(success_code)
                self.log.bind(
                    uri=request.uri,
                    code=request.code
                ).msg('Request succeeded')
                return result

            d = defer.maybeDeferred(f, self, request, *args, **kwargs)
            d.addCallback(_succeed, request)
            return d
        return _
    return decorator


def bind_log(f):
    """
    Binds keyword arguments to log
    """
    @wraps(f)
    def _(self, request, log, *args, **kwargs):
        bound_log = log.bind(**kwargs)
        return f(self, request, bound_log, *args, **kwargs)
    return _


def log_arguments(f):
    """
    Binds all arguments that are not 'self' or 'request' to self.log
    """
    @wraps(f)
    def _(self, request, *args, **kwargs):
        self.log = self.log.bind(**kwargs)
        return f(self, request, *args, **kwargs)
    return _


def log_ignore_arguments(*ignore):
    """
    Binds all arguments that are not 'self' or 'request' to self.log

    :param ignore: parameters to be ignored when logging
    """
    def wrapper(f):
        @wraps(f)
        def _(self, request, *args, **kwargs):
            revised_kwargs = {key: kwargs[key] for key in kwargs
                              if key not in ignore}
            self.log = self.log.bind(**revised_kwargs)
            return f(self, request, *args, **kwargs)
        return _
    return wrapper


def with_transaction_id():
    """
    Adds a transaction id to the request, and update application log.
    """
    def decorator(f):
        @wraps(f)
        def _(self, request, *args, **kwargs):
            transaction_id = generate_transaction_id()
            request.setHeader('X-Response-Id', transaction_id)
            self.log = self.log.bind(
                system=reflect.fullyQualifiedName(f),
                transaction_id=transaction_id,
                request_ip=request.getClientIP())
            self.log.bind(
                method=request.method,
                uri=request.uri,
                clientproto=request.clientproto,
                referer=request.getHeader("referer"),
                useragent=request.getHeader("user-agent")
            ).msg("Received request")
            return f(self, request, *args, **kwargs)
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
        def _(self, request, *args, **kwargs):
            try:
                request.content.seek(0)
                data = json.loads(request.content.read())
                validate(data, schema)
            except ValueError as e:
                return defer.fail(InvalidJsonError())
            except ValidationError, e:
                return defer.fail(e)
            kwargs['data'] = data
            return f(self, request, *args, **kwargs)

        return _
    return decorator


class InvalidQueryArgument(Exception):
    """
    Something is wrong with a query arg
    """


def paginatable(f):
    """
    Is a paginatable endpoint, which means that it accepts the limit and marker
    query args.  This decorator validates them and puts them into a pagination
    dictionary.  It also sets a default limit based on the config value for
    the pagination limit, if no query argument for limit is passed.

    If a pagination limit is passed that exceeds the hard limit or is less than
    1, it is coerced into the correct range.
    """
    @wraps(f)
    def _(self, request, *args, **kwargs):
        paginate = {}
        hard_limit = config_value('limits.pagination')
        if 'limit' in request.args:
            try:
                paginate['limit'] = int(request.args['limit'][0])
            except:
                return defer.fail(InvalidQueryArgument(
                    'Invalid query argument for "limit"'))

            paginate['limit'] = max(min(paginate['limit'], hard_limit), 1)
        else:
            paginate['limit'] = hard_limit

        if 'marker' in request.args:
            paginate['marker'] = request.args['marker'][0]

        kwargs['paginate'] = paginate
        return f(self, request, *args, **kwargs)
    return _


class AuditLogger(object):
    """
    An object mainly for storing the results of audit loggable info while
    within the decorated function.  Also will audit-log the
    """
    def __init__(self, log):
        self._params = {}
        self.set_logger(log)

    def set_logger(self, log):
        """
        Sets the logger to a new bound log
        """
        self._logger = audit(log)

    def add(self, **kwargs):
        """
        Add new structured data to be logged in the audit log
        """
        self._params.update(kwargs)

    def audit(self, message):
        self._logger.msg(message, **self._params)


def auditable(event_type, msg_on_success):
    """
    Makes the result of an endpoint audit loggable - passes an
    AuditLogger object to the handler so that it can set extra data to be
    logged.
    """
    def decorator(f):
        @wraps(f)
        def _(self, request, *args, **kwargs):
            audit_logger = AuditLogger(self.log)
            audit_logger.add(event_type=event_type)
            kwargs['audit_logger'] = audit_logger

            d = defer.maybeDeferred(f, self, request, *args, **kwargs)

            def audit_log_it(result):
                audit_logger.audit(msg_on_success)
                return result

            return d.addCallback(audit_log_it)
        return _
    return decorator
