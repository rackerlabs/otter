"""
A wrapper around treq to log all requests along with the status code and time
it took.
"""
from functools import wraps
from uuid import uuid4

import attr

import treq

from twisted.internet import reactor

from otter.log import log as default_log
from otter.util.deferredutils import timeout_deferred


_treq_request_methods = ('get', 'head', 'post', 'put', 'delete',
                         'patch', 'request')


@attr.s
class LoggingTreq(object):
    """
    A class that wraps treq and calls all of its request methods and logs
    the request and the response, including the time the request took to
    finish.

    :ivar clock: - a reactor to use for timing requests - will use the default
        reactor if not provided.
    :ivar log: - a BoundLog instance - will use the default BoundLog instance
        in :obj:`otter.log` if not provided.
    :ivar log_response: - a boolean as to whether or not the response bodies
        should be logged as bytes.  Defaults to False, because this can be
        dangerous as it may log secret information such as admin passwords.
    """
    clock = attr.ib(default=reactor)
    log = attr.ib(default=default_log)
    log_response = attr.ib(default=False)

    def __getattr__(self, name):
        """
        Handle anything else that should be on treq.
        """
        return getattr(treq, name)

    def request(self, method, url, **kwargs):
        """Wrapper around :py:func:`treq.request` that logs the request."""
        return self.log_request(treq.request)(url, method=method, **kwargs)

    def head(self, url, headers=None, **kwargs):
        """Wrapper around :py:func:`treq.head` that logs the request."""
        return self.log_request(treq.head)(url, headers=headers, **kwargs)

    def get(self, url, headers=None, **kwargs):
        """Wrapper around :py:func:`treq.get` that logs the request."""
        return self.log_request(treq.get)(url, headers=headers, **kwargs)

    def post(self, url, data=None, **kwargs):
        """Wrapper around :py:func:`treq.post` that logs the request."""
        return self.log_request(treq.post)(url, data=data, **kwargs)

    def put(self, url, data=None, **kwargs):
        """Wrapper around :py:func:`treq.put` that logs the request."""
        return self.log_request(treq.put)(url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        """Wrapper around :py:func:`treq.patch` that logs the request."""
        return self.log_request(treq.patch)(url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        """Wrapper around :py:func:`treq.delete` that logs the request."""
        return self.log_request(treq.delete)(url, **kwargs)

    def log_request(self, treq_call):
        """
        A decorator around a treq request that logs information.

        Supported non-treq keyword arguments::

        - ``clock`` - a reactor to use for timing requests - will use the
            default reactor if not provided.
        - ``log`` - a BoundLog instance - will use the default BoundLog
            instance in :obj:`otter.log` if not provided.

        Note that the `headers` are modified to include a treq-specific request
        ID.
        """
        @wraps(treq_call)
        def wrapper(url, **kwargs):
            clock = kwargs.pop('clock', self.clock)
            log = kwargs.pop('log', self.log)

            method = kwargs.get('method', treq_call.__name__)

            kwargs.setdefault('headers', {})
            if kwargs['headers'] is None:
                kwargs['headers'] = {}

            treq_transaction = str(uuid4())
            kwargs['headers']['x-otter-request-id'] = [treq_transaction]

            log = log.bind(system='treq.request', url=url, method=method,
                           url_params=kwargs.get('params'),
                           treq_request_id=treq_transaction)
            start_time = clock.seconds()

            log.msg("Request to {method} {url} starting.")
            d = treq_call(url=url, **kwargs)

            timeout_deferred(d, 45, clock)

            def log_request(response):
                kwargs = {'request_time': clock.seconds() - start_time,
                          'status_code': response.code,
                          'headers': response.headers}
                message = (
                    "Request to {method} {url} resulted in a {status_code} "
                    "response after {request_time} seconds.")

                if self.log_response:
                    return (
                        treq.content(response)
                        .addCallback(
                            lambda b: log.msg(message, response_body=b,
                                              **kwargs))
                        .addCallback(lambda _: response))

                log.msg(message, **kwargs)
                return response

            def log_failure(failure):
                request_time = clock.seconds() - start_time
                log.msg("Request to {method} {url} failed after "
                        "{request_time} seconds.",
                        reason=failure, request_time=request_time)
                return failure

            return d.addCallbacks(log_request, log_failure)
        return wrapper


_logging_treq = LoggingTreq()


# these methods just wrap logging_treq
request = _logging_treq.request
head = _logging_treq.head
get = _logging_treq.get
post = _logging_treq.post
put = _logging_treq.put
patch = _logging_treq.patch
delete = _logging_treq.delete

json_content = treq.json_content
content = treq.content
text_content = treq.text_content


__version__ = treq.__version__
