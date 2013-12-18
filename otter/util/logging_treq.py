"""
A wrapper around treq to log all requests along with the status code and time
it took.
"""

import treq

from twisted.internet import reactor

from otter.log import log as default_log


def _log_request(treq_call, url, **kwargs):
    """
    Log a treq request, including the time it took and the status code.

    :param callable f: a ``treq`` request method, such as ``treq.request``, or
        ``treq.get``, ``treq.post``, etc.
    """
    time_func = kwargs.pop('time_function', reactor.seconds)
    log = kwargs.pop('log', default_log)
    method = kwargs.get('method', treq_call.__name__)

    start_time = time_func()
    d = treq_call(url=url, **kwargs)

    def log_request(response):
        request_time = time_func() - start_time
        log.msg(
            ("Request to {method} {url} resulted in a {status_code} response "
             "after {request_time} seconds."),
            url=url, status_code=response.code, headers=response.headers,
            request_time=request_time, system="treq.request", method=method)
        return response

    def log_failure(failure):
        request_time = time_func() - start_time
        log.msg("Request to {method} {url} failed after {request_time} seconds.",
                url=url, reason=failure, request_time=request_time,
                method=method, system="treq.request")
        return failure

    return d.addCallbacks(log_request, log_failure)


def request(method, url, **kwargs):
    """
    Wrapper around :method:`treq.request` that logs the request.

    See :py:func:`treq.request`
    """
    return _log_request(treq.request, url, method=method, **kwargs)


def head(url, headers=None, **kwargs):
    """
    Wrapper around :method:`treq.head` that logs the request.

    See :py:func:`treq.head`
    """
    return _log_request(treq.head, url, headers=headers, **kwargs)


def get(url, headers=None, **kwargs):
    """
    Wrapper around :method:`treq.get` that logs the request.

    See :py:func:`treq.get`
    """
    return _log_request(treq.get, url, headers=headers, **kwargs)


def post(url, data=None, **kwargs):
    """
    Wrapper around :method:`treq.post` that logs the request.

    See :py:func:`treq.post`
    """
    return _log_request(treq.post, url, data=data, **kwargs)


def put(url, data=None, **kwargs):
    """
    Wrapper around :method:`treq.put` that logs the request.

    See :py:func:`treq.put`
    """
    return _log_request(treq.put, url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    """
    Wrapper around :method:`treq.patch` that logs the request.

    See :py:func:`treq.patch`
    """
    return _log_request(treq.patch, url, data=data, **kwargs)


def delete(url, **kwargs):
    """
    Wrapper around :method:`treq.delete` that logs the request.

    See :py:func:`treq.delete`
    """
    return _log_request(treq.delete, url, **kwargs)


json_content = treq.json_content
content = treq.content
text_content = treq.text_content


__version__ = treq.__version__
