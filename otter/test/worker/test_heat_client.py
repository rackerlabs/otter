"""Tests for the asynchronous Heat client."""

import json
import mock

from twisted.trial.unittest import TestCase

from otter.util.http import APIError
from otter.worker.heat_client import HeatClient, OpenStackClient
from otter.test.utils import stub_treq, StubLog


class HeatClientTests(TestCase):
    """Tests for HeatClient."""

    def _assert_bound(self, log, **kwargs):
        self.assertEqual(log.binds, kwargs)

    def _http_client(self, code, json_content):
        treq = stub_treq(code, json.dumps(json_content))
        return OpenStackClient(treq, lambda: None, auth_token='my-auth-token')

    def test_create_stack(self):
        """
        create_stack POSTs data to the stack creation endpoint and returns
        the parsed JSON result.
        """
        log = StubLog()
        http = self._http_client(code=201,
                                 json_content={'hello': 'world'})
        treq = http.treq
        client = HeatClient(log, http)
        result = client.create_stack(
            'http://heat-url/', 'my-stack-name', {'p1': 'v1'}, 60,
            'my template')

        self.assertEqual(
            http.treq.requests,
            [{'method': 'post',
              'url': 'http://heat-url/stacks',
              'headers': {'x-auth-token': ['my-auth-token'],
                          'content-type': ['application/json'],
                          'accept': ['application/json'],
                          'User-Agent': ['OtterScale/0.0']},
              'data': json.dumps({'stack_name': 'my-stack-name',
                                  'parameters': {'p1': 'v1'},
                                  'timeout_mins': 60,
                                  'template': 'my template'}),
              'log': mock.ANY}])

        self.assertEqual(self.successResultOf(result), {'hello': 'world'})
        self._assert_bound(http.treq.requests[-1]['log'],
                           system='heatclient', event='create-stack',
                           stack_name='my-stack-name')

    def test_create_stack_error(self):
        """
        On any result other than 201, create_stack raises an exception.
        """
        log = StubLog()
        http = self._http_client(code=404,
                                 json_content={'hello': 'world'})
        client = HeatClient(log, http)
        result = client.create_stack(
            'http://heat-url/', 'my-stack-name', {'p1': 'v1'}, 60,
            'my template')
        failure = self.failureResultOf(result)
        failure.trap(APIError)

    def test_update_stack(self):
        """
        update_stack PUTs data to the stack endpoint and returns
        the parsed JSON result.
        """
        log = StubLog()
        http = self._http_client(code=202, json_content={'hello': 'world'})
        client = HeatClient(log, http)
        result = client.update_stack(
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')
        self.assertEqual(
            http.treq.requests,
            [{'method': 'put',
              'url': 'http://heat-url/my-stack',
              'headers': {'x-auth-token': ['my-auth-token'],
                          'content-type': ['application/json'],
                          'accept': ['application/json'],
                          'User-Agent': ['OtterScale/0.0']},
              'data': json.dumps({
                  'parameters': {'p1': 'v1'},
                  'timeout_mins': 60,
                  'template': 'my template'}),
              'log': mock.ANY}])

        self.assertEqual(self.successResultOf(result), {'hello': 'world'})
        self._assert_bound(http.treq.requests[-1]['log'],
                           system='heatclient', event='update-stack')

    def test_update_stack_error(self):
        """Non-202 codes from updating a stack are considered an APIError."""
        log = StubLog()
        http = self._http_client(code=204, json_content={'hello': 'world'})
        client = HeatClient(log, http)
        result = client.update_stack(
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')
        failure = self.failureResultOf(result)
        failure.trap(APIError)

    def test_get_stack(self):
        """get_stack performs a GET on the given stack URL."""
        log = StubLog()
        http = self._http_client(code=200, json_content={'hello': 'world'})
        client = HeatClient(log, http)
        result = client.get_stack('http://heat-url/my-stack')
        self.assertEqual(
            http.treq.requests,
            [{'method': 'get',
              'url': 'http://heat-url/my-stack',
              'headers': {'x-auth-token': ['my-auth-token'],
                          'content-type': ['application/json'],
                          'accept': ['application/json'],
                          'User-Agent': ['OtterScale/0.0']},
              'data': None,
              'log': mock.ANY}])
        self.assertEqual(self.successResultOf(result), {'hello': 'world'})
        self._assert_bound(http.treq.requests[-1]['log'],
                           system='heatclient', event='get-stack')

    def test_get_stack_error(self):
        """Non-200 codes from getting a stack are considered an APIError."""
        log = StubLog()
        http = self._http_client(code=201, json_content={'hello': 'world'})
        client = HeatClient(log, http)
        result = client.get_stack('http://heat-url/my-stack')
        failure = self.failureResultOf(result)
        failure.trap(APIError)
