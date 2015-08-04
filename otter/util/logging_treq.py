"""
A wrapper around treq to log all requests along with the status code and time
it took.
"""
from uuid import uuid4

import treq

from twisted.internet import reactor

from otter.log import log as default_log
from otter.util.deferredutils import timeout_deferred


def _log_request(treq_call, url, **kwargs):
    """
    Log a treq request, including the time it took and the status code.

    :param callable f: a ``treq`` request method, such as ``treq.request``, or
        ``treq.get``, ``treq.post``, etc.
    :param log: If provided, an instance of BoundLog.
        Defaults to ``otter.log.default_log`` if not provided.
    :type log: BoundLog or None.

    Supported non-treq keyword arguments::

    - ``clock`` - a reactor to use for timing requests - will use the default
        reactor if not provided.
    - ``log`` - a BoundLog instance - will use the default BoundLog instance
        in :obj:`otter.log` if not provided.
    - ``log_response`` - a boolean as to whether or not the response bodies
        should be logged as bytes.  Defaults to False, because this can be
        dangerous as it may log secret information such as admin passwords.

    Note that the `headers` are modified to include a treq-specific request ID.
    """
    clock = kwargs.pop('clock', reactor)
    log = kwargs.pop('log', None)
    log_response = kwargs.pop('log_response', False)

    if not log:
        log = default_log
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
            "Request to {method} {url} resulted in a {status_code} response "
            "after {request_time} seconds.")

        if log_response:
            return (
                treq.content(response)
                .addCallback(
                    lambda b: log.msg(message, response_body=b, **kwargs))
                .addCallback(lambda _: response))

        log.msg(message, **kwargs)
        return response

    def log_failure(failure):
        request_time = clock.seconds() - start_time
        log.msg("Request to {method} {url} failed after {request_time} "
                "seconds.",
                reason=failure, request_time=request_time)
        return failure

    return d.addCallbacks(log_request, log_failure)


def request(method, url, **kwargs):
    """
    Wrapper around :meth:`treq.request` that logs the request.

    See :py:func:`treq.request`
    """
    return _log_request(treq.request, url, method=method, **kwargs)


def head(url, headers=None, **kwargs):
    """
    Wrapper around :meth:`treq.head` that logs the request.

    See :py:func:`treq.head`
    """
    return _log_request(treq.head, url, headers=headers, **kwargs)


def get(url, headers=None, **kwargs):
    """
    Wrapper around :meth:`treq.get` that logs the request.

    See :py:func:`treq.get`
    """
    return _log_request(treq.get, url, headers=headers, **kwargs)


def post(url, data=None, **kwargs):
    """
    Wrapper around :meth:`treq.post` that logs the request.

    See :py:func:`treq.post`
    """
    return _log_request(treq.post, url, data=data, **kwargs)


def put(url, data=None, **kwargs):
    """
    Wrapper around :meth:`treq.put` that logs the request.

    See :py:func:`treq.put`
    """
    return _log_request(treq.put, url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    """
    Wrapper around :meth:`treq.patch` that logs the request.

    See :py:func:`treq.patch`
    """
    return _log_request(treq.patch, url, data=data, **kwargs)


def delete(url, **kwargs):
    """
    Wrapper around :meth:`treq.delete` that logs the request.

    See :py:func:`treq.delete`
    """
    return _log_request(treq.delete, url, **kwargs)


json_content = treq.json_content
content = treq.content
text_content = treq.text_content


__version__ = treq.__version__
