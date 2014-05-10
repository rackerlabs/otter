"""
Asynchronous client for Heat, using treq.
"""

from __future__ import print_function

import json

from otter.util.http import (append_segments, headers, check_success,
                             APIError)


__all__ = ['HeatClient']


class Request(object):
    """
    An immutable representation of a request.
    """
    # I just want this to be a PersistentDict with perform() as a plain
    # function, but OO is the thing to do.
    def __init__(self, method, url, headers=None, data=None):
        self.method = method
        self.url = url
        self.headers = headers if headers is not None else {}
        self.data = data

    def perform(self, log, treq, headers):
        """
        Perform the request with the given treq client.

        :param log: A bound log to pass on to treq.
        :param treq: The treq object.
        :param headers: Additional late-bound headers. Typically used for
            the X-Auth-Token.
        """
        func = getattr(treq, self.method)
        req_headers = self.headers.copy()
        req_headers.update(headers)
        return func(self.url, headers=req_headers, data=self.data, log=log)


class ReauthenticationFailed(Exception):
    """
    Raised when an HTTP request returned 401 even after successful
    reauthentication was performed.
    """


class OpenStackClient(object):
    def __init__(self, treq, reauth, auth_token=None):
        self.treq = treq
        self.reauth = reauth
        self.auth_token = auth_token

    def _request_with_reauth(self, log, request, repeats=1):
        """
        Perform a request and automatically handle reauthentication.

        If an HTTP 401 is returned, the `reauth` function will be called, and
        when the returned Deferred fires, the request will be repeated.

        If repeating the request fails, :class:`ReauthenticationFailed` will
        be raised.
        """
        def _got_reauth_result(response):
            return self._request_with_reauth(log, request, repeats - 1)

        def _got_result(response):
            if response.code == 401:
                if repeats == 0:
                    raise ReauthenticationFailed()
                reauth_result = self.reauth()
                reauth_result.addCallback(_got_reauth_result)
                reauth_result.addErrback(_got_reauth_error)
                return reauth_result
            else:
                return response

        standard_headers = headers(self.auth_token)
        result = request.perform(log, self.treq, standard_headers)
        result.addCallback(_got_result)
        return result

    def json_request(self, log, method, url, headers=None, data=None,
                     success=(200,)):
        """
        Do a request, check the response code, and parse the JSON result.

        :param log: A bound log to pass on to the treq client.
        :param method: The HTTP method to invoke.
        :param url: As treq accepts.
        :param headers: As treq accepts.
        :param data: As treq accepts.
        :param list success: The list of HTTP codes to consider successful.
        """
        request = Request(
            method,
            url,
            data=data,
            headers=headers)
        result = self._request_with_reauth(log, request)
        result.addCallback(check_success, success, self.treq)
        result.addCallback(self.treq.json_content)
        return result


class HeatClient(object):
    """
    An Asynchronous Heat client.
    """
    def __init__(self, log, http):
        self.http = http
        self.log = log.bind(system='heatclient')

    def create_stack(self, heat_url, stack_name, parameters, timeout,
                     template):
        """Create a stack."""
        payload = {
            'stack_name': stack_name,
            'parameters': parameters,
            'timeout_mins': timeout,
            'template': template
        }
        log = self.log.bind(event='create-stack', stack_name=stack_name)
        return self.http.json_request(
            log,
            'post',
            append_segments(heat_url, 'stacks'),
            data=json.dumps(payload),
            success=[201])

    def update_stack(self, stack_url, parameters, timeout, template):
        """Update a stack."""
        payload = {
            'parameters': parameters,
            'timeout_mins': timeout,
            'template': template,
        }
        log = self.log.bind(event='update-stack')
        return self.http.json_request(
            log,
            'put',
            stack_url,
            data=json.dumps(payload),
            success=[202])

    def get_stack(self, stack_url):
        """Get the metadata about a stack."""
        log = self.log.bind(event='get-stack')
        return self.http.json_request(
            log,
            'get', stack_url)


def main(reactor, *args):
    """
    Try to get a stack, then update it. If no stack exists, it will be created.
    """
    import os
    import yaml
    from otter.log import log

    template = yaml.safe_load(open(args[1]))
    tenant = os.environ['OS_TENANT_ID']
    client = HeatClient(os.environ['OS_AUTH_TOKEN'], log)

    heat_root = 'https://dfw.orchestration.api.rackspacecloud.com/v1/' + tenant
    stack_url = heat_root + '/stacks/my-stack-name'
    result = client.get_stack(stack_url)

    def got_stack(result):
        print("here's a stack:", result)
        result = client.update_stack(stack_url, None, None,
                                     {}, 60, template=template)
        return result

    def no_stack(failure):
        failure.trap(APIError)
        if failure.value.code != 404:
            return failure
        result = client.create_stack(
            heat_root,
            'my-stack-name', None, None, {}, 60, False, template=template)
        return result

    result.addCallback(got_stack).addErrback(no_stack)
    return result.addCallback(lambda r: print("FINAL RESULT", r))


if __name__ == '__main__':
    import sys
    from twisted.internet.task import react
    from twisted.python.log import addObserver
    from otter.log.setup import observer_factory
    addObserver(observer_factory())
    react(main, sys.argv)
