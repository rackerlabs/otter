"""Tests for the asynchronous Heat client."""

import json
import mock

from effect.testing import resolve_effect

from testtools import TestCase

from otter.util.http import APIError, headers
from otter.util.pure_http import OSHTTPClient, Request
from otter.worker.heat_client import HeatClient
from otter.test.utils import SameJSON, stub_pure_response, IsBoundWith, mock_log


class HeatClientTests(TestCase):
    """Tests for HeatClient."""

    def _http_client(self):
        return OSHTTPClient(lambda: 1 / 0)

    def test_create_stack(self):
        """
        create_stack POSTs data to the stack creation endpoint and returns
        the parsed JSON result.
        """
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.create_stack(
            'my-auth-token', 'http://heat-url/', 'my-stack-name',
            {'p1': 'v1'}, 60, 'my template')

        req = eff.intent
        self.assertEqual(req.method, 'post')

        self.assertEqual(
            req,
            Request(
                method='post',
                url='http://heat-url/stacks',
                headers=headers('my-auth-token'),
                data=SameJSON({
                    'stack_name': 'my-stack-name',
                    'parameters': {'p1': 'v1'},
                    'timeout_mins': 60,
                    'template': 'my template'}),
                log=mock.ANY))

        # Currently, json response is returned directly.
        self.assertEqual(
            resolve_effect(
                eff,
                stub_pure_response(json.dumps({'hello': 'world'}), 201)),
           {'hello': 'world'})

        self.assertThat(
            req.log,
            IsBoundWith(system='heatclient',
                        event='create-stack',
                        stack_name='my-stack-name'))

    def test_create_stack_error(self):
        """
        On any result other than 201, create_stack raises an exception.
        """
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.create_stack(
            'my-token', 'http://heat-url/', 'my-stack-name', {'p1': 'v1'}, 60,
            'my template')
        self.assertRaises(APIError, resolve_effect, eff,
                          stub_pure_response('', 500))

    def test_update_stack(self):
        """
        update_stack PUTs data to the stack endpoint and returns
        the parsed JSON result.
        """
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.update_stack(
            'my-auth-token',
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')
        self.assertEqual(
            eff.intent,
            Request(method='put',
                    url='http://heat-url/my-stack',
                    headers=headers('my-auth-token'),
                    data=SameJSON({
                        'parameters': {'p1': 'v1'},
                        'timeout_mins': 60,
                        'template': 'my template'}),
                    log=mock.ANY))

        # Currently, json response is returned directly.
        self.assertEqual(
            resolve_effect(
                eff,
                stub_pure_response(json.dumps({'hello': 'world'}), code=202)),
            {'hello': 'world'})
        self.assertThat(
            eff.intent.log,
            IsBoundWith(system='heatclient', event='update-stack'))

    def test_update_stack_error(self):
        """Non-202 codes from updating a stack are considered an APIError."""
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.update_stack(
            'my-auth-token',
            'http://heat-url/my-stack', {'p1': 'v1'}, 60,
            'my template')

        self.assertRaises(
            APIError,
            resolve_effect, eff, stub_pure_response('', code=200))

    def test_get_stack(self):
        """get_stack performs a GET on the given stack URL."""
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.get_stack('my-auth-token', 'http://heat-url/my-stack')
        self.assertEqual(
            eff.intent,
            Request(method='get',
                    url='http://heat-url/my-stack',
                    headers=headers('my-auth-token'),
                    data=None,
                    log=mock.ANY))
        # Currently, json response is returned directly.
        self.assertEqual(
            resolve_effect(
                eff,
                stub_pure_response(json.dumps({'hello': 'world'}), code=200)),
            {'hello': 'world'})
        self.assertThat(
            eff.intent.log,
            IsBoundWith(system='heatclient', event='get-stack'))

    def test_get_stack_error(self):
        """Non-200 codes from getting a stack are considered an APIError."""
        log = mock_log()
        http = self._http_client()
        client = HeatClient(log, http)
        eff = client.get_stack('my-auth-token', 'http://heat-url/my-stack')
        self.assertRaises(
            APIError,
            resolve_effect, eff, stub_pure_response('', code=201))
