"""Tests for the asynchronous Heat client."""

import json
import mock

from twisted.trial.unittest import TestCase

from otter.util.http import APIError
from otter.worker.heat_client import HeatClient
from otter.test.utils import mock_treq, mock_log, patch


class HeatClientTests(TestCase):
    """Tests for HeatClient."""

    def _assert_bound(self, orig_log, log, **kwargs):
        # Invoke a log message on the mocked log object so that we can check
        # which keys were bound to the log...
        log.msg()
        orig_log.msg.assert_called_once_with(**kwargs)

    def _treq(self, **kwargs):
        treq = mock_treq(**kwargs)
        patch(self, 'otter.util.http.treq', new=treq)
        return treq

    def test_create_stack(self):
        """
        create_stack POSTs data to the stack creation endpoint and returns
        the parsed JSON result.
        """
        log = mock_log()
        treq = self._treq(code=201, method='post',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
        result = client.create_stack(
            'http://heat-url/', 'my-stack-name', {'p1': 'v1'}, 60,
            'my template')
        treq.post.assert_called_once_with(
            'http://heat-url/stacks',
            headers={'x-auth-token': ['my-auth-token'],
                     'content-type': ['application/json'],
                     'accept': ['application/json'],
                     'User-Agent': ['OtterScale/0.0']},
            data=json.dumps({'stack_name': 'my-stack-name',
                             'parameters': {'p1': 'v1'},
                             'timeout_mins': 60,
                             'template': 'my template'}),
            log=mock.ANY)

        self.assertEqual(self.successResultOf(result), {'hello': 'world'})
        self._assert_bound(log, treq.post.mock_calls[-1][2]['log'],
                           heatclient=True, event='create-stack',
                           stack_name='my-stack-name')

    def test_create_stack_error(self):
        """
        On any result other than 201, create_stack raises an exception.
        """
        log = mock_log()
        treq = self._treq(code=404, method='post',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
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
        log = mock_log()
        treq = self._treq(code=202, method='put',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
        result = client.update_stack(
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')
        treq.put.assert_called_once_with(
            'http://heat-url/my-stack',
            headers={'x-auth-token': ['my-auth-token'],
                     'content-type': ['application/json'],
                     'accept': ['application/json'],
                     'User-Agent': ['OtterScale/0.0']},
            data=json.dumps({
                'parameters': {'p1': 'v1'},
                'timeout_mins': 60,
                'template': 'my template'}),
            log=mock.ANY)

        self.assertEqual(self.successResultOf(result), {'hello': 'world'})
        self._assert_bound(log, treq.put.mock_calls[-1][2]['log'],
                           heatclient=True, event='update-stack')

    def test_update_stack_error(self):
        """Non-202 codes from updating a stack are considered an APIError."""
        log = mock_log()
        treq = self._treq(code=204, method='put',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
        result = client.update_stack(
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')
        failure = self.failureResultOf(result)
        failure.trap(APIError)

    def test_get_stack(self):
        """get_stack performs a GET on the given stack URL."""
        log = mock_log()
        treq = self._treq(code=200, method='get',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
        result = client.get_stack('http://heat-url/my-stack')
        self.assertEqual(self.successResultOf(result), {'hello': 'world'})

    def test_get_stack_error(self):
        """Non-200 codes from getting a stack are considered an APIError."""
        log = mock_log()
        treq = self._treq(code=201, method='get',
                          json_content={'hello': 'world'})
        client = HeatClient('my-auth-token', log, treq)
        result = client.get_stack('http://heat-url/my-stack')
        failure = self.failureResultOf(result)
        failure.trap(APIError)
