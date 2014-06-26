"""
Asynchronous client for Heat, using treq.
"""

from __future__ import print_function

import json

from otter.util.http import append_segments
from otter.util.pure_http import request


__all__ = ['HeatClient']


class HeatClient(object):
    """A purely functional Heat client. Action methods return Effects."""

    def __init__(self, log, request):
        self.log = log.bind(system='heatclient')
        self.request = request

    # auth_token is passed to each of these functions individually instead of
    # being set as an attribute of the object because a reauth can happen at
    # any time, and we shouldn't be stuck caching the old one here. It's the
    # caller's responsibility to fetch it from storage every time a request is
    # to be made.

    def create_stack(self, heat_url, stack_name, parameters,
                     timeout, template):
        """Create a stack."""
        payload = {
            'stack_name': stack_name,
            'parameters': parameters,
            'timeout_mins': timeout,
            'template': template
        }
        log = self.log.bind(event='create-stack', stack_name=stack_name)
        return self.request(
            'post', append_segments(heat_url, 'stacks'),
            data=payload, log=log, success_codes=[201])

    def update_stack(self, stack_url, parameters, timeout,
                     template):
        """Update a stack."""
        payload = {
            'parameters': parameters,
            'timeout_mins': timeout,
            'template': template,
        }
        log = self.log.bind(event='update-stack')
        return self.request('put', stack_url, data=payload, log=log,
                            success_codes=[202])

    def get_stack(self, stack_url):
        """Get the metadata about a stack."""
        log = self.log.bind(event='get-stack')
        return self.request('get', stack_url, log=log, success_codes=[200])


def main(reactor, *args):
    """
    Try to get a stack, then update it. If no stack exists, it will be created.
    """
    import os
    import yaml
    from otter.log import log
    from otter.util.http import APIError

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
