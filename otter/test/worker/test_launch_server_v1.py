"""
Unittests for the launch_server_v1 launch config.
"""

import mock
import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.web.http_headers import Headers

from otter.worker.launch_server_v1 import (
    APIError,
    check_success,
    append_segments,
    auth_headers,
    private_ip_addresses,
    endpoints,
    add_to_load_balancer,
    add_to_load_balancers,
    server_details,
    wait_for_status,
    create_server
)


fake_service_catalog = [
    {'type': 'compute',
     'name': 'openStackCompute',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
         {'region': 'ORD', 'publicURL': 'http://ord.openstack/'}
     ]},
    {'type': 'database',
     'name': 'CaasaaS',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.cass/'},
     ]}
]


class UtilityTests(TestCase):
    """
    Tests for non-specific utilities that should be refactored out of the worker
    implementation eventually.
    """

    def setUp(self):
        """
        set up test dependencies for utilities.
        """
        self.treq_patcher = mock.patch('otter.worker.launch_server_v1.treq')
        self.treq = self.treq_patcher.start()
        self.addCleanup(self.treq_patcher.stop)

    def test_api_error(self):
        """
        An APIError will be instantiated with an HTTP Code and an HTTP response
        body and will expose these in public attributes and have a reasonable
        string representation.
        """
        e = APIError(404, "Not Found.")

        self.assertEqual(e.code, 404)
        self.assertEqual(e.body, "Not Found.")
        self.assertEqual(str(e), "API Error code=404, body='Not Found.'")

    def test_check_success(self):
        """
        check_success will return the response if the response.code is in success_codes.
        """
        response = mock.Mock()
        response.code = 201

        self.assertEqual(check_success(response, [200, 201]), response)

    def test_check_success_non_success_code(self):
        """
        check_success will return a deferred that errbacks with an APIError
        if the response.code is not in success_codes.
        """
        response = mock.Mock()
        response.code = 404
        self.treq.content.return_value = succeed('Not Found.')

        d = check_success(response, [200, 201])
        f = self.failureResultOf(d)

        self.assertTrue(f.check(APIError))
        self.assertEqual(f.value.code, 404)
        self.assertEqual(f.value.body, 'Not Found.')

    def test_append_segments(self):
        """
        append_segments will append an arbitrary number of path segments to
        a base url even if there is a trailing / on the base uri.
        """
        expected = 'http://example.com/foo/bar/baz'
        self.assertEqual(
            append_segments('http://example.com', 'foo', 'bar', 'baz'),
            expected
        )

        self.assertEqual(
            append_segments('http://example.com/', 'foo', 'bar', 'baz'),
            expected
        )

    def test_append_segments_unicode(self):
        """
        append_segments will convert to utf-8 and quote unicode path segments.
        """
        self.assertEqual(
            append_segments('http://example.com', u'\u2603'),
            'http://example.com/%E2%98%83'
        )

    def test_append_segments_quote(self):
        """
        append_segments will quote all path segments.
        """
        self.assertEqual(
            append_segments('http://example.com', 'foo bar'),
            'http://example.com/foo%20bar'
        )

    def test_auth_headers_content_type(self):
        """
        auth_headers will use a json content-type.
        """
        self.assertEqual(
            auth_headers('any')['content-type'], ['application/json'])

    def test_auth_headers_accept(self):
        """
        auth_headers will use a json accept header.
        """
        self.assertEqual(
            auth_headers('any')['accept'], ['application/json'])

    def test_auth_headers_sets_auth_token(self):
        """
        auth_headers will set the X-Auth-Token header based on it's auth_token
        argument.
        """
        self.assertEqual(
            auth_headers('my-auth-token')['x-auth-token'], ['my-auth-token'])

    def test_auth_headers_can_be_http_headers(self):
        """
        auth_headers will produce a result that can be passed to
        twisted.web.http_headers.Headers.
        """
        headers = Headers(auth_headers('my-auth-token'))
        self.assertIsInstance(headers, Headers)

    def test_private_ip_addresses(self):
        """
        private_ip_addresses returns all private IPv4 addresses from a
        complete server body.
        """
        addresses = {
            'private': [
                {'addr': '10.0.0.1', 'version': 4},
                {'addr': '10.0.0.2', 'version': 4},
                {'addr': '::1', 'version': 6}
            ],
            'public': [
                {'addr': '50.50.50.50', 'version': 4},
                {'addr': '::::', 'version': 6}
            ]}

        result = private_ip_addresses({'server': {'addresses': addresses}})
        self.assertEqual(result, ['10.0.0.1', '10.0.0.2'])

    def test_endpoints(self):
        """
        endpoints will return all endpoints with no arguments.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog)),
            sorted([{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
                    {'region': 'ORD', 'publicURL': 'http://ord.openstack/'},
                    {'region': 'DFW', 'publicURL': 'http://dfw.cass/'}]))

    def test_endpoints_limit_region(self):
        """
        endpoints will return all endpoints that have the specified region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, region='DFW')),
            sorted([{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
                    {'region': 'DFW', 'publicURL': 'http://dfw.cass/'}]))

    def test_endpoints_limit_type(self):
        """
        endpoints will return all endpoints that have the specified type.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, service_type='database')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.cass/'}])

    def test_endpoints_limit_name(self):
        """
        endpoints will return only the named endpoints.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, service_name='CaasaaS')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.cass/'}])

    def test_endpoints_region_and_name(self):
        """
        endpoints will return only the named endpoint in a specific region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             service_name='openStackCompute',
                             region='DFW')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'}])

    def test_endpoints_region_and_type(self):
        """
        endpoints will return only the endpoints of the specified type,
        in the specified region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             service_type='compute',
                             region='ORD')),
            [{'region': 'ORD', 'publicURL': 'http://ord.openstack/'}])

    def test_endpoints_name_and_type(self):
        """
        endpoints will return only the endpoints of the specified name
        and type.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             service_type='compute',
                             service_name='openStackCompute')),
            sorted([{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
                    {'region': 'ORD', 'publicURL': 'http://ord.openstack/'}]))


expected_headers = {
    'content-type': ['application/json'],
    'accept': ['application/json'],
    'x-auth-token': ['my-auth-token']
}


error_body = '{"code": 500, "message": "Internal Server Error"}'


class LoadBalancersTests(TestCase):
    """
    Test adding to one or more load balancers.
    """
    def setUp(self):
        """
        set up test dependencies for load balancers.
        """
        treq_patcher = mock.patch('otter.worker.launch_server_v1.treq')
        self.treq = treq_patcher.start()
        self.addCleanup(treq_patcher.stop)

    def test_add_to_load_balancer(self):
        """
        add_to_load_balancer will make a properly formed post request to
        the specified load balancer endpoint witht he specified auth token,
        load balancer id, port, and ip address.
        """
        response = mock.Mock()
        response.code = 200
        self.treq.post.return_value = succeed(response)

        content = mock.Mock()
        self.treq.json_content.return_value = succeed(content)

        d = add_to_load_balancer('http://url/', 'my-auth-token',
                                 {'loadBalancerId': '12345',
                                  'port': 80},
                                 '192.168.1.1')

        result = self.successResultOf(d)
        self.assertEqual(result, content)

        self.treq.post.assert_called_once_with(
            'http://url/loadbalancers/12345/nodes',
            headers=expected_headers,
            data=mock.ANY
        )

        data = self.treq.post.mock_calls[0][2]['data']

        self.assertEqual(json.loads(data),
                         {'nodes': [{'address': '192.168.1.1',
                                     'port': 80,
                                     'condition': 'ENABLED',
                                     'type': 'PRIMARY'}]})

        self.treq.json_content.assert_called_once_with(response)

    def test_add_to_load_balancer_propogates_api_failure(self):
        """
        add_to_load_balancer will propogate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.post.return_value = succeed(response)

        self.treq.content.return_value = succeed(error_body)

        d = add_to_load_balancer('http://url/', 'my-auth-token',
                                 {'loadBalancerId': '12345',
                                  'port': 80},
                                 '192.168.1.1')

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancer')
    def test_add_to_load_balancers(self, add_to_load_balancer):
        """
        Add to load balancers will call add_to_load_balancer multiple times and
        for each load balancer configuration and return all of the results.
        """
        def _succeed(*args, **kwargs):
            return succeed(True)

        add_to_load_balancer.side_effect = _succeed

        d = add_to_load_balancers('http://url/', 'my-auth-token',
                                  [{'loadBalancerId': '12345',
                                    'port': 80},
                                   {'loadBalancerId': '54321',
                                    'port': 81}],
                                  '192.168.1.1')

        results = self.successResultOf(d)

        self.assertEqual(results, [True, True])


class ServerTests(TestCase):
    """
    Test server manipulation functions.
    """
    def setUp(self):
        """
        Set up test dependencies.
        """
        treq_patcher = mock.patch('otter.worker.launch_server_v1.treq')
        self.treq = treq_patcher.start()
        self.addCleanup(treq_patcher.stop)

    def test_server_details(self):
        """
        server_details will perform a properly formed GET request against
        the server endpoint and return the decoded json content.
        """
        response = mock.Mock()
        response.code = 200

        self.treq.get.return_value = succeed(response)

        d = server_details('http://url/', 'my-auth-token', 'serverId')

        results = self.successResultOf(d)

        self.assertEqual(results, self.treq.json_content.return_value)

    def test_server_details_propogates_api_failure(self):
        """
        server_details will propogate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.get.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = server_details('http://url/', 'my-auth-token', 'serverId')

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)

    def test_create_server(self):
        """
        create_server will perform a properly formed POST request to the
        server endpoint and return the decoded json content.
        """
        response = mock.Mock()
        response.code = 202

        self.treq.post.return_value = succeed(response)

        server_config = {
            'name': 'someServer',
            'imageRef': '1',
            'flavorRef': '3'
        }

        d = create_server('http://url/', 'my-auth-token', 'scalingGroup', server_config)

        result = self.successResultOf(d)

        self.assertEqual(result, self.treq.json_content.return_value)

    def test_create_server_propogates_api_failure(self):
        """
        create_server will propogate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.post.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = create_server('http://url/', 'my-auth-token', 'scalingGroup', {})

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_status(self, server_details):
        """
        wait_for_status will poll server_details until the status transitions
        to our expected status at which point it will return the complete
        server_details.
        """
        clock = Clock()

        server_status = ['BUILDING']

        def _server_status(*args, **kwargs):
            return succeed({'server': {'status': server_status[0]}})

        server_details.side_effect = _server_status

        d = wait_for_status('http://url/', 'my-auth-token', 'serverId', 'ACTIVE',
                            clock=clock)

        server_details.assert_called_with('http://url/', 'my-auth-token', 'serverId')
        self.assertEqual(server_details.call_count, 1)

        server_status[0] = 'ACTIVE'

        clock.advance(5)

        server_details.assert_called_with('http://url/', 'my-auth-token', 'serverId')
        self.assertEqual(server_details.call_count, 2)

        result = self.successResultOf(d)

        self.assertEqual(result['server']['status'], server_status[0])
