"""
Unittests for the launch_server_v1 launch config.
"""
import mock
import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import CancelledError, Deferred, fail, succeed
from twisted.internet.task import Clock

from otter.worker.launch_server_v1 import (
    private_ip_addresses,
    endpoints,
    add_to_load_balancer,
    add_to_load_balancers,
    server_details,
    wait_for_active,
    create_server,
    launch_server,
    prepare_launch_config,
    delete_server,
    remove_from_load_balancer,
    public_endpoint_url,
    UnexpectedServerStatus,
    verified_delete
)


from otter.test.utils import DummyException, mock_log, patch
from otter.util.http import APIError, RequestError, wrap_request_error
from otter.util.config import set_config_data
from otter.util.deferredutils import unwrap_first_error

fake_config = {
    'regionOverrides': {},
    'cloudServersOpenStack': 'cloudServersOpenStack',
    'cloudLoadBalancers': 'cloudLoadBalancers'
}

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
    Tests for non-specific utilities that should be refactored out of the
    worker implementation eventually.
    """

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
        endpoints will return only the named endpoint in a specific region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             'cloudServersOpenStack',
                             'DFW')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'}])

    def test_public_endpoint_url(self):
        """
        public_endpoint_url returns the first publicURL for the named service
        in a specific region.
        """
        self.assertEqual(
            public_endpoint_url(fake_service_catalog, 'cloudServersOpenStack',
                                'DFW'),
            'http://dfw.openstack/')


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
        self.treq = patch(self, 'otter.worker.launch_server_v1.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

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
                                 {'loadBalancerId': 12345,
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

    def test_add_to_load_balancer_propagates_api_failure(self):
        """
        add_to_load_balancer will propagate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.post.return_value = succeed(response)

        self.treq.content.return_value = succeed(error_body)

        d = add_to_load_balancer('http://url/', 'my-auth-token',
                                 {'loadBalancerId': 12345,
                                  'port': 80},
                                 '192.168.1.1')

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancer')
    def test_add_to_load_balancers(self, add_to_load_balancer):
        """
        Add to load balancers will call add_to_load_balancer multiple times and
        for each load balancer configuration and return all of the results.
        """
        d1 = Deferred()
        d2 = Deferred()
        add_to_load_balancer_deferreds = [d1, d2]

        def _add_to_load_balancer(endpoint, auth_token, lb_config, ip_address):
            # Include the ID and port in the response so that we can verify
            # that add_to_load_balancers associates the response with the correct
            # load balancer.
            return add_to_load_balancer_deferreds.pop(0)

        add_to_load_balancer.side_effect = _add_to_load_balancer

        d = add_to_load_balancers('http://url/', 'my-auth-token',
                                  [{'loadBalancerId': 12345,
                                    'port': 80},
                                   {'loadBalancerId': 54321,
                                    'port': 81}],
                                  '192.168.1.1')

        d2.callback((54321, 81))
        d1.callback((12345, 80))

        results = self.successResultOf(d)

        self.assertEqual(sorted(results), [(12345, (12345, 80)),
                                           (54321, (54321, 81))])

    def test_remove_from_load_balancer(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node.
        """
        response = mock.Mock()
        response.code = 200

        self.treq.delete.return_value = succeed(response)

        d = remove_from_load_balancer('http://url/', 'my-auth-token', 12345, 1)
        self.assertEqual(self.successResultOf(d), None)

        self.treq.delete.assert_called_once_with(
            'http://url/loadbalancers/12345/nodes/1',
            headers=expected_headers)

    def test_remove_from_load_balancer_propagates_api_failure(self):
        """
        remove_from_load_balancer will propagate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.delete.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = remove_from_load_balancer('http://url/', 'my-auth-token',
                                      '12345', '1')
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)


class ServerTests(TestCase):
    """
    Test server manipulation functions.
    """
    def setUp(self):
        """
        Set up test dependencies.
        """
        self.log = mock_log()
        set_config_data(fake_config)
        self.addCleanup(set_config_data, {})

        self.treq = patch(self, 'otter.worker.launch_server_v1.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

        self.generate_server_name = patch(
            self,
            'otter.worker.launch_server_v1.generate_server_name')
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

    def test_server_details_propagates_api_failure(self):
        """
        server_details will propagate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.get.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = server_details('http://url/', 'my-auth-token', 'serverId')

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)

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

    def test_create_server_propagates_api_failure(self):
        """
        create_server will propagate API failures.
        """
        response = mock.Mock()
        response.code = 500

        self.treq.post.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = create_server('http://url/', 'my-auth-token', {})

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active(self, server_details):
        """
        wait_for_active will poll server_details until the status transitions
        to our expected status at which point it will return the complete
        server_details.
        """
        clock = Clock()

        server_status = ['BUILD']

        def _server_status(*args, **kwargs):
            return succeed({'server': {'status': server_status[0]}})

        server_details.side_effect = _server_status

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            clock=clock)

        server_details.assert_called_with('http://url/', 'my-auth-token',
                                          'serverId')
        self.assertEqual(server_details.call_count, 1)

        server_status[0] = 'ACTIVE'

        clock.advance(5)

        server_details.assert_called_with('http://url/', 'my-auth-token',
                                          'serverId')
        self.assertEqual(server_details.call_count, 2)

        result = self.successResultOf(d)

        self.assertEqual(result['server']['status'], server_status[0])

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_errors(self, server_details):
        """
        wait_for_active will errback it's Deferred if it encounters a non-active
        state transition.
        """
        clock = Clock()

        server_status = ['BUILD', 'ERROR']

        def _server_status(*args, **kwargs):
            return succeed({'server': {'status': server_status.pop(0)}})

        server_details.side_effect = _server_status

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            clock=clock)

        clock.advance(5)

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(UnexpectedServerStatus))

        self.assertEqual(failure.value.server_id, 'serverId')
        self.assertEqual(failure.value.status, 'ERROR')
        self.assertEqual(failure.value.expected_status, 'ACTIVE')

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_stops_looping_on_error(self, server_details):
        """
        wait_for_active stops looping when it encounters an error.
        """
        clock = Clock()
        server_status = ['BUILD', 'ERROR']

        def _server_status(*args, **kwargs):
            return succeed({'server': {'status': server_status.pop(0)}})

        server_details.side_effect = _server_status

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            clock=clock)

        # This gets called once immediately then every 5 seconds.
        self.assertEqual(server_details.call_count, 1)

        clock.advance(5)

        self.assertEqual(server_details.call_count, 2)

        clock.advance(5)

        # This has not been called a 3rd time because we encountered an error,
        # and the looping call stopped.
        self.assertEqual(server_details.call_count, 2)

        self.failureResultOf(d)

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_stops_looping_on_success(self, server_details):
        """
        wait_for_active stops looping when it encounters the active state.
        """
        clock = Clock()
        server_status = ['BUILD', 'ACTIVE']

        def _server_status(*args, **kwargs):
            return succeed({'server': {'status': server_status.pop(0)}})

        server_details.side_effect = _server_status

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            clock=clock)

        # This gets called once immediately then every 5 seconds.
        self.assertEqual(server_details.call_count, 1)

        clock.advance(5)

        self.assertEqual(server_details.call_count, 2)

        clock.advance(5)

        # This has not been called a 3rd time because we encountered the active
        # state and the looping call stopped.
        self.assertEqual(server_details.call_count, 2)

        self.successResultOf(d)

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_stops_looping_on_timeout(self, server_details):
        """
        wait_for_active stops looping when the timeout passes
        """
        clock = Clock()
        server_details.side_effect = lambda *args, **kwargs: succeed(
            {'server': {'status': 'BUILD'}})

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            interval=5, timeout=6, clock=clock)

        # This gets called once immediately then every 5 seconds.
        self.assertEqual(server_details.call_count, 1)
        clock.advance(5)
        self.assertEqual(server_details.call_count, 2)
        self.assertNoResult(d)

        clock.advance(1)
        self.failureResultOf(d, CancelledError)
        # instance id was previously bound by launch_server
        self.log.msg.assert_called_with(mock.ANY, timeout=6, time_building=6)

        # the loop has stopped
        clock.advance(5)
        self.assertEqual(server_details.call_count, 2)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server(self, wait_for_active, create_server,
                           add_to_load_balancers):
        """
        launch_server creates a server, waits until the server is active then
        adds the server's first private IPv4 address to any load balancers.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': [
                             {'loadBalancerId': 12345, 'port': 80},
                             {'loadBalancerId': 54321, 'port': 81}
                         ]}

        load_balancer_metadata = {
            'rax:auto_scaling_server_name': 'as000000',
            'rax:auto_scaling_group_id': '1111111-11111-11111-11111111'}

        prepared_load_balancers = [
            {'loadBalancerId': 12345, 'port': 80,
             'metadata': load_balancer_metadata},
            {'loadBalancerId': 54321, 'port': 81,
             'metadata': load_balancer_metadata}
        ]

        expected_server_config = {
            'imageRef': '1', 'flavorRef': '1', 'name': 'as000000',
            'metadata': {
                'rax:auto_scaling_group_id': '1111111-11111-11111-11111111'}}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_active.return_value = succeed(server_details)

        add_to_load_balancers.return_value = succeed([
            (12345, ('10.0.0.1', 80)),
            (54321, ('10.0.0.1', 81))
        ])

        d = launch_server(self.log,
                          'DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        result = self.successResultOf(d)
        self.assertEqual(
            result,
            (server_details, [
                (12345, ('10.0.0.1', 80)),
                (54321, ('10.0.0.1', 81))]))

        create_server.assert_called_once_with('http://dfw.openstack/',
                                              'my-auth-token',
                                              expected_server_config)

        wait_for_active.assert_called_once_with(mock.ANY,
                                                'http://dfw.openstack/',
                                                'my-auth-token',
                                                '1')

        add_to_load_balancers.assert_called_once_with(
            'http://dfw.lbaas/', 'my-auth-token', prepared_load_balancers,
            '10.0.0.1')

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_propagates_create_server_errors(
            self, wait_for_active, create_server, add_to_load_balancers):
        """
        launch_server will propagate any errors from create_server.
        """
        create_server.return_value = fail(
            APIError(500, "Oh noes")).addErrback(wrap_request_error, 'url')

        d = launch_server(self.log,
                          'DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          {'server': {}})

        failure = self.failureResultOf(d)
        failure.trap(RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, "Oh noes")

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_propagates_wait_for_active_errors(
            self, wait_for_active, create_server, add_to_load_balancers):
        """
        launch_server will propagate any errors from wait_for_active.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_active.return_value = fail(
            APIError(500, "Oh noes")).addErrback(wrap_request_error, 'url')

        d = launch_server(self.log,
                          'DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        failure = self.failureResultOf(d)
        failure.trap(RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, "Oh noes")

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_propagates_add_to_load_balancers_errors(
            self, wait_for_active, create_server, add_to_load_balancers):
        """
        launch_server will propagate any errors from add_to_load_balancers.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_active.return_value = succeed(server_details)

        add_to_load_balancers.return_value = fail(
            APIError(500, "Oh noes")).addErrback(wrap_request_error, 'url')

        d = launch_server(self.log,
                          'DFW',
                          self.scaling_group,
                          fake_service_catalog,
                          'my-auth-token',
                          launch_config)

        failure = self.failureResultOf(d)
        failure.trap(RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, "Oh noes")


class ConfigPreparationTests(TestCase):
    """
    Test config preparation.
    """
    def setUp(self):
        """
        Configure mocks.
        """
        generate_server_name_patcher = mock.patch(
            'otter.worker.launch_server_v1.generate_server_name')
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

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_name, launch_config['server']['name'])

    def test_server_name_no_suffix(self):
        """
        No server name in the launch config means no suffix.
        """
        test_config = {'server': {}}
        expected_name = 'as000000'

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_name, launch_config['server']['name'])

    def test_server_metadata(self):
        """
        The auto scaling group should be added to the server metadata.
        """
        test_config = {'server': {}}
        expected_metadata = {
            'rax:auto_scaling_group_id': self.scaling_group_uuid}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_metadata,
                         launch_config['server']['metadata'])

    def test_server_merge_metadata(self):
        """
        The auto scaling metadata should be merged with specified metadata.
        """
        test_config = {'server': {'metadata': {'foo': 'bar'}}}
        expected_metadata = {
            'rax:auto_scaling_group_id': self.scaling_group_uuid,
            'foo': 'bar'}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_metadata,
                         launch_config['server']['metadata'])

    def test_load_balancer_metadata(self):
        """
        auto scaling group and auto scaling server name should be
        added to the node metadata for a load balancer.
        """
        test_config = {'server': {}, 'loadBalancers': [{'id': 1, 'port': 80}]}

        expected_metadata = {
            'rax:auto_scaling_group_id': self.scaling_group_uuid,
            'rax:auto_scaling_server_name': 'as000000'}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_metadata,
                         launch_config['loadBalancers'][0]['metadata'])

    def test_load_balancer_metadata_merge(self):
        """
        auto scaling metadata should be merged with user specified metadata.
        """
        test_config = {'server': {}, 'loadBalancers': [
            {'id': 1, 'port': 80, 'metadata': {'foo': 'bar'}}]}

        expected_metadata = {
            'rax:auto_scaling_group_id': self.scaling_group_uuid,
            'rax:auto_scaling_server_name': 'as000000',
            'foo': 'bar'}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_metadata,
                         launch_config['loadBalancers'][0]['metadata'])

    def test_launch_config_is_copy(self):
        """
        The input launch config is not mutated by prepare_launch_config.
        """
        test_config = {'server': {}}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertNotIdentical(test_config, launch_config)


# An instance associated with a single load balancer.
instance_details = (
    'a',
    [(12345, {'nodes': [{'id': 1}]}),
     (54321, {'nodes': [{'id': 2}]})])


class DeleteServerTests(TestCase):
    """
    Test the delete server worker.
    """
    def setUp(self):
        """
        Set up some mocks.
        """
        set_config_data(fake_config)
        self.addCleanup(set_config_data, {})

        self.log = mock_log()
        self.treq = patch(self, 'otter.worker.launch_server_v1.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

    @mock.patch('otter.worker.launch_server_v1.remove_from_load_balancer')
    def test_delete_server_deletes_load_balancer_node(
            self, remove_from_load_balancer):
        """
        delete_server removes the nodes specified in instance details from
        the associated load balancers.
        """
        remove_from_load_balancer.return_value = succeed(None)

        d = delete_server(self.log,
                          'DFW',
                          fake_service_catalog,
                          'my-auth-token',
                          instance_details)
        self.successResultOf(d)

        remove_from_load_balancer.has_calls([
            mock.call('http://dfw.lbaas/', 'my-auth-token', 12345, 1),
            mock.call('http://dfw.lbaas/', 'my-auth-token', 54321, 2)
        ], any_order=True)

        self.assertEqual(remove_from_load_balancer.call_count, 2)

    @mock.patch('otter.worker.launch_server_v1.remove_from_load_balancer')
    def test_delete_server(self, remove_from_load_balancer):
        """
        delete_server performs a DELETE request against the instance URL based
        on the information in instance_details.
        """
        remove_from_load_balancer.return_value = succeed(None)

        d = delete_server(self.log, 'DFW', fake_service_catalog,
                          'my-auth-token', instance_details)
        self.successResultOf(d)

        self.treq.delete.assert_called_once_with(
            'http://dfw.openstack/servers/a', headers=expected_headers)

    @mock.patch('otter.worker.launch_server_v1.remove_from_load_balancer')
    def test_delete_server_propagates_loadbalancer_failures(
            self, remove_from_load_balancer):
        """
        delete_server propagates any errors from removing server from load
        balancers
        """
        remove_from_load_balancer.return_value = fail(
            APIError(500, '')).addErrback(wrap_request_error, 'url')

        d = delete_server(self.log, 'DFW', fake_service_catalog,
                          'my-auth-token', instance_details)
        failure = unwrap_first_error(self.failureResultOf(d))

        self.assertEqual(failure.value.reason.value.code, 500)

    @mock.patch('otter.worker.launch_server_v1.remove_from_load_balancer')
    def test_delete_server_propagates_delete_server_api_failures(
            self, remove_from_load_balancer):
        """
        delete_server fails with an APIError if deleting the server fails.
        """

        remove_from_load_balancer.return_value = succeed(None)

        response = mock.Mock()
        response.code = 500

        self.treq.delete.return_value = succeed(response)
        self.treq.content.return_value = succeed(error_body)

        d = delete_server(self.log, 'DFW', fake_service_catalog,
                          'my-auth-token', instance_details)
        failure = self.failureResultOf(d)

        self.assertEqual(failure.value.reason.value.code, 500)

    def test_verified_delete_returns_after_delete_but_verifies_deletion(self):
        """
        verified_delete returns as soon as the deletion succeeded, but also
        attempts to verify deleting the server.  It also logs the deletion.
        """
        clock = Clock()
        self.treq.delete.return_value = succeed(
            mock.Mock(spec=['code'], code=204))

        self.treq.head.return_value = Deferred()

        d = verified_delete(self.log, 'http://url/', 'my-auth-token',
                            'serverId', clock=clock)
        self.assertIsNone(self.successResultOf(d))

        self.treq.delete.assert_called_once_with('http://url/servers/serverId',
                                                 headers=expected_headers)
        self.treq.head.assert_called_once_with('http://url/servers/serverId',
                                               headers=expected_headers)

        self.log.msg.assert_called_with(mock.ANY, instance_id='serverId')

    def test_verified_delete_propagates_delete_server_api_failures(self):
        """
        verified_delete propagates deletions from server deletion
        """
        clock = Clock()
        self.treq.delete.return_value = succeed(
            mock.Mock(spec=['code'], code=500))
        self.treq.content.return_value = succeed(error_body)
        self.treq.head.return_value = Deferred()

        d = verified_delete(self.log, 'http://url/', 'my-auth-token',
                            'serverId', clock=clock)
        failure = self.failureResultOf(d, RequestError)
        self.assertEqual(failure.value.reason.value.code, 500)

    def test_verified_delete_does_not_propagate_verification_failure(self):
        """
        verified_delete propagates deletions from server deletion
        """
        clock = Clock()
        self.treq.delete.return_value = succeed(
            mock.Mock(spec=['code'], code=204))
        self.treq.head.return_value = fail(DummyException('failure'))
        self.treq.content.side_effect = lambda *args: succeed("")

        d = verified_delete(self.log, 'http://url/', 'my-auth-token',
                            'serverId', clock=clock)
        self.assertIsNone(self.successResultOf(d))

    def test_verified_delete_retries_verification_until_success(self):
        """
        If the first verification didn't work, wait a bit and see if it's been
        deleted, since a server can sit in DELETE state for a bit.

        It also logs deletion success, and deletion failure
        """
        clock = Clock()
        self.treq.delete.return_value = succeed(
            mock.Mock(spec=['code'], code=204))
        self.treq.content.side_effect = lambda *args: succeed("")
        self.treq.head.return_value = Deferred()

        verified_delete(self.log, 'http://url/', 'my-auth-token',
                        'serverId', interval=5, clock=clock)

        self.assertEqual(self.log.msg.call_count, 1)
        self.treq.head.return_value.callback(mock.Mock(spec=['code'], code=204))

        self.treq.head.assert_called_once_with('http://url/servers/serverId',
                                               headers=expected_headers)

        self.treq.head.return_value = succeed(
            mock.Mock(spec=['code'], code=404))

        clock.advance(5)
        self.treq.head.assert_has_calls([
            mock.call('http://url/servers/serverId', headers=expected_headers),
            mock.call('http://url/servers/serverId', headers=expected_headers)
        ])
        self.assertEqual(self.log.msg.call_count, 2)

        # the loop has stopped
        clock.advance(5)
        self.assertEqual(self.treq.head.call_count, 2)

    def test_verified_delete_retries_verification_until_timeout(self):
        """
        If the verification fails until the timeout, log a failure and do not
        keep trying to verify.
        """
        clock = Clock()
        self.treq.delete.return_value = succeed(
            mock.Mock(spec=['code'], code=204))
        self.treq.content.side_effect = lambda *args: succeed("")
        self.treq.head.side_effect = lambda *args, **kwargs: succeed(
            mock.Mock(spec=['code'], code=204))

        verified_delete(self.log, 'http://url/', 'my-auth-token',
                        'serverId', interval=5, timeout=11, clock=clock)

        clock.advance(11)
        self.treq.head.assert_has_calls([
            mock.call('http://url/servers/serverId', headers=expected_headers),
            mock.call('http://url/servers/serverId', headers=expected_headers)
        ])
        self.log.err.assert_called_once_with(
            None, instance_id="serverId", why=mock.ANY, timeout=11,
            time_delete=11)

        # the loop has stopped
        clock.advance(5)
        self.assertEqual(self.treq.head.call_count, 2)
