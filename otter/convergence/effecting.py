"""Code related to effecting change based on a convergence plan."""

from effect import parallel
from otter.util.pure_http import has_code


def _reqs_to_effect(request_func, conv_requests):
    """Turns a collection of :class:`Request` objects into an effect.

    :param request_func: A pure-http request function, as produced by
        :func:`otter.http.get_request_func`.
    :param conv_requests: Convergence requests to turn into effects.
    :return: An effect which will perform all the requests in parallel.
    :rtype: :class:`Effect`
    """
    effects = [request_func(service_type=r.service,
                            method=r.method,
                            url=r.path,
                            headers=r.headers,
                            data=r.data,
                            success_pred=has_code(*r.success_codes))
               for r in conv_requests]
    return parallel(effects)


def steps_to_effect(request_func, steps):
    """Turns a collection of :class:`IStep` providers into an effect."""
    return _reqs_to_effect(request_func, [s.as_request() for s in steps])
