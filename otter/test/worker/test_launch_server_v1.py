"""
Unittests for the launch_server_v1 launch config.
"""

import mock
import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed, fail
from twisted.internet.task import Clock
from twisted.web.http_headers import Headers

from otter.worker.launch_server_v1 import (
    APIError,
    check_success,
    auth_headers,
    private_ip_addresses,
    endpoints,
    add_to_load_balancer,
    add_to_load_balancers,
    server_details,
    wait_for_status,
    create_server,
    launch_server,
    prepare_launch_config
)


fake_service_catalog = [
    {'type': 'compute',
     'name': 'cloudServersOpenStack',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
         {'region': 'ORD', 'publicURL': 'http://ord.openstack/'}
     ]},
    {'type': 'lb',
     'name': 'cloudLoadBalancers',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'},
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
                    {'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'}]))

    def test_endpoints_limit_region(self):
        """
        endpoints will return all endpoints that have the specified region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, region='DFW')),
            sorted([{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
                    {'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'}]))

    def test_endpoints_limit_type(self):
        """
        endpoints will return all endpoints that have the specified type.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, service_type='lb')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'}])

    def test_endpoints_limit_name(self):
        """
        endpoints will return only the named endpoints.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog, service_name='cloudLoadBalancers')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'}])

    def test_endpoints_region_and_name(self):
        """
        endpoints will return only the named endpoint in a specific region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             service_name='cloudServersOpenStack',
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
                             service_name='cloudServersOpenStack')),
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

        generate_server_name_patcher = mock.patch('otter.worker.launch_server_v1.generate_server_name')
        self.generate_server_name = generate_server_name_patcher.start()
        self.addCleanup(generate_server_name_patcher.stop)
        self.generate_server_name.return_value = 'as000000'

        self.scaling_group_uuid = '1111111-11111-11111-11111111'

        self.scaling_group = mock.Mock(uuid=self.scaling_group_uuid)

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

        d = create_server('http://url/', 'my-auth-token', server_config)

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

        d = create_server('http://url/', 'my-auth-token', {})

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

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_status')
    def test_launch_server(self, wait_for_status, create_server, add_to_load_balancers):
        """
        launch_server creates a server, waits until the server is active then
        adds the server's first private IPv4 address to any load balancers.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        expected_server_config = {
            'imageRef': '1', 'flavorRef': '1', 'name': 'as000000',
            'metadata': {'rax:auto_scaling_group_id': '1111111-11111-11111-11111111'}}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [{'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_status.return_value = succeed(server_details)

        add_to_load_balancers.return_value = succeed([])

        d = launch_server('DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        self.successResultOf(d)  # TODO: Currently the return value is not significant.

        create_server.assert_called_once_with('http://dfw.openstack/',
                                              'my-auth-token',
                                              expected_server_config)

        wait_for_status.assert_called_once_with('http://dfw.openstack/',
                                                'my-auth-token',
                                                '1',
                                                'ACTIVE')

        add_to_load_balancers.assert_called_once_with(
            'http://dfw.lbaas/', 'my-auth-token', [], '10.0.0.1')

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_status')
    def test_launch_server_propogates_create_server_errors(
            self, wait_for_status, create_server, add_to_load_balancers):
        """
        launch_server will propogate any errors from create_server.
        """
        create_server.return_value = fail(APIError(500, "Oh noes"))

        d = launch_server('DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          {'server': {}})

        failure = self.failureResultOf(d)
        failure.trap(APIError)

        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, "Oh noes")

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_status')
    def test_launch_server_propogates_wait_for_status_errors(
            self, wait_for_status, create_server, add_to_load_balancers):
        """
        launch_server will propogate any errors from wait_for_status.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [{'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_status.return_value = fail(APIError(500, "Oh noes"))

        d = launch_server('DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        failure = self.failureResultOf(d)
        failure.trap(APIError)

        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, "Oh noes")

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_status')
    def test_launch_server_propogates_add_to_load_balancers_errors(
            self, wait_for_status, create_server, add_to_load_balancers):
        """
        launch_server will propogate any errors from add_to_load_balancers.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [{'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_status.return_value = succeed(server_details)

        add_to_load_balancers.return_value = fail(APIError(500, "Oh noes"))

        d = launch_server('DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        failure = self.failureResultOf(d)
        failure.trap(APIError)

        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, "Oh noes")


class ConfigPreparationTests(TestCase):
    """
    Test config preparation.
    """
    def setUp(self):
        """
        Configure mocks.
        """
        generate_server_name_patcher = mock.patch('otter.worker.launch_server_v1.generate_server_name')
        self.generate_server_name = generate_server_name_patcher.start()
        self.addCleanup(generate_server_name_patcher.stop)
        self.generate_server_name.return_value = 'as000000'

        self.scaling_group_uuid = '1111111-11111-11111-11111111'

    def test_server_name_suffix(self):
        """
        The server name uses the name specified in the launch config as a
        suffix.
        """
        test_config = {'server': {'name': 'web.example.com'}}
        expected_name = 'as000000-web.example.com'

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_name, launch_config['server']['name'])

    def test_server_name_no_suffix(self):
        """
        No server name in the launch config means no suffix.
        """
        test_config = {'server': {}}
        expected_name = 'as000000'

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_name, launch_config['server']['name'])

    def test_server_metadata(self):
        """
        The auto scaling group should be added to the server metadata.
        """
        test_config = {'server': {}}
        expected_metadata = {'rax:auto_scaling_group_id': self.scaling_group_uuid}

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_metadata, launch_config['server']['metadata'])

    def test_server_merge_metadata(self):
        """
        The auto scaling metadata should be merged with specified metadata.
        """
        test_config = {'server': {'metadata': {'foo': 'bar'}}}
        expected_metadata = {'rax:auto_scaling_group_id': self.scaling_group_uuid,
                             'foo': 'bar'}

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_metadata, launch_config['server']['metadata'])

    def test_load_balancer_metadata(self):
        """
        auto scaling group and auto scaling server name should be
        added to the node metadata for a load balancer.
        """
        test_config = {'server': {}, 'loadBalancers': [{'id': 1, 'port': 80}]}

        expected_metadata = {'rax:auto_scaling_group_id': self.scaling_group_uuid,
                             'rax:auto_scaling_server_name': 'as000000'}

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_metadata, launch_config['loadBalancers'][0]['metadata'])

    def test_load_balancer_metadata_merge(self):
        """
        auto scaling metadata should be merged with user specified metadata.
        """
        test_config = {'server': {}, 'loadBalancers': [
            {'id': 1, 'port': 80, 'metadata': {'foo': 'bar'}}]}

        expected_metadata = {'rax:auto_scaling_group_id': self.scaling_group_uuid,
                             'rax:auto_scaling_server_name': 'as000000',
                             'foo': 'bar'}

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertEqual(expected_metadata, launch_config['loadBalancers'][0]['metadata'])

    def test_launch_config_is_copy(self):
        """
        The input launch config is not mutated by prepare_launch_config.
        """
        test_config = {'server': {}}

        launch_config = prepare_launch_config(self.scaling_group_uuid, test_config)

        self.assertNotIdentical(test_config, launch_config)
