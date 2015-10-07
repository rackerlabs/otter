"""
Unittests for the launch_server_v1 launch config.
"""
import json
from functools import partial

from urllib import urlencode
from urlparse import urlunsplit

import mock

from testtools.matchers import IsInstance, MatchesRegex, StartsWith

from toolz.dicttoolz import merge

from twisted.internet.defer import Deferred, fail, succeed
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import headers
from otter.supervisor import RequestBag
from otter.test.utils import (
    CheckFailure,
    DummyException,
    IsBoundWith,
    StubResponse,
    StubTreq,
    StubTreq2,
    defaults_by_name,
    iMock,
    matches,
    mock_log,
    mock_treq,
    patch)
from otter.test.worker.test_rcv3 import _rcv3_add_response_body
from otter.undo import IUndoStack
from otter.util.config import set_config_data
from otter.util.deferredutils import TimedOutError, unwrap_first_error
from otter.util.http import APIError, RequestError, wrap_request_error
from otter.worker import launch_server_v1
from otter.worker.launch_server_v1 import (
    CLBOrNodeDeleted,
    LB_MAX_RETRIES,
    LB_RETRY_INTERVAL_RANGE,
    ServerCreationRetryError,
    ServerDeleted,
    UnexpectedServerStatus,
    _as_new_style_instance_details,
    _definitely_lb_config,
    _remove_from_clb,
    _without_otter_metadata,
    add_to_clb,
    add_to_load_balancer,
    add_to_load_balancers,
    create_server,
    delete_and_verify,
    delete_server,
    find_server,
    launch_server,
    prepare_launch_config,
    remove_from_load_balancer,
    scrub_otter_metadata,
    server_details,
    verified_delete,
    wait_for_active
)


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
     ]},
    {'type': 'orchestration',
     'name': 'cloudOrchestration',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.orch/'},
     ]}
]


def expected_headers(auth_token='my-auth-token'):
    """
    Return an expected set of headers, given an auth token
    """
    return {
        'content-type': ['application/json'],
        'accept': ['application/json'],
        'x-auth-token': [auth_token],
        'User-Agent': ['OtterScale/0.0']
    }

error_body = '{"code": 500, "message": "Internal Server Error"}'


class RequestBagTestMixin(object):
    """
    A test case mixin for test cases that require a request bag.
    """
    def setUp(self):
        """
        Do the necessary set-up for a request_func-using test case.
        """
        super(RequestBagTestMixin, self).setUp()
        self.tenant_id = '111111'
        self.bags = []

        def new_bag(counter=0):
            bag = RequestBag(
                lb_region="DFW",
                region="DFW",
                dispatcher=mock.Mock(),
                tenant_id=self.tenant_id,
                auth_token="my-auth-token{0}".format(counter),
                service_catalog=fake_service_catalog,
                re_auth=partial(new_bag, counter + 1),
            )
            self.bags.append(bag)
            return succeed(bag)

        self.request_bag = self.successResultOf(new_bag())
        self.bags.pop()  # remove the first

        self.server_details = {
            'server': {
                "id": "my-server-id",
                "addresses": {
                    'private': [
                        {'addr': '192.168.1.1', 'version': 4},
                        {'addr': '192.168.1.2', 'version': 4},
                        {'addr': '10.0.0.1', 'version': 4},
                        {'addr': '::1', 'version': 6}
                    ],
                    'public': [
                        {'addr': '50.50.50.50', 'version': 4},
                        {'addr': '::::', 'version': 6}
                    ]
                }
            }
        }


class LoadBalancersTestsMixin(RequestBagTestMixin):
    """
    Test adding and removing nodes from load balancers
    """

    def setUp(self):
        """
        set up test dependencies for load balancers.
        """
        super(LoadBalancersTestsMixin, self).setUp()
        self.log = mock_log()
        self.log.msg.return_value = None

        self.undo = iMock(IUndoStack)

        self.max_retries = 12
        set_config_data(merge({'worker': {'lb_max_retries': self.max_retries,
                                          'lb_retry_interval_range': [5, 7]}},
                              fake_config))
        self.addCleanup(set_config_data, {})

        # patch random_interval
        self.retry_interval = 6
        self.rand_interval = patch(self, 'otter.worker.launch_server_v1.random_interval')
        self.rand_interval.return_value = self.interval_func = mock.Mock(
            return_value=self.retry_interval)

        self.clock = Clock()


lb_config_1 = {'loadBalancerId': 12345, 'port': 80}
lb_config_2 = {'loadBalancerId': 54321, 'port': 81}
lb_response_1 = {'nodes': [{'id': 'a', 'address': '192.168.1.1'}]}
lb_response_2 = {'nodes': [{'id': 'b', 'address': '192.168.1.1'}]}


class AddToCLBTests(LoadBalancersTestsMixin, SynchronousTestCase):
    """
    Tests for :func:`add_to_clb`.
    """

    def setUp(self):
        """
        Mock treq.post for adding nodes
        """
        super(AddToCLBTests, self).setUp()
        self.auth_token = self.request_bag.auth_token
        self.json_content = {'nodes': [{'id': 1}]}
        self.treq = patch(self, 'otter.worker.launch_server_v1.treq',
                          new=mock_treq(code=200,
                                        json_content=self.json_content,
                                        content='{"message": "bad"}',
                                        method='post'))
        patch(self, 'otter.util.http.treq', new=self.treq)
        self.lb_config = {'loadBalancerId': 12345, 'port': 80}

    def _add_to_clb(self):
        """
        Helper function to call :func:`add_to_clb`.
        """
        return add_to_clb(self.log, 'http://dfw.lbaas/', self.auth_token,
                          self.lb_config, '192.168.1.1', self.undo,
                          clock=self.clock)

    def test_add_to_clb(self):
        """
        :func:`add_to_clb` will make a properly formed post request to
        the specified load balancer endpoint with the specified auth token,
        load balancer id, port, and ip address.
        """
        result = self.successResultOf(self._add_to_clb())
        self.assertEqual(result, self.json_content)

        self.treq.post.assert_called_once_with(
            'http://dfw.lbaas/loadbalancers/12345/nodes',
            headers=expected_headers(self.auth_token),
            data=mock.ANY,
            log=matches(IsInstance(self.log.__class__))
        )

        data = self.treq.post.mock_calls[0][2]['data']

        self.assertEqual(json.loads(data),
                         {'nodes': [{'address': '192.168.1.1',
                                     'port': 80,
                                     'condition': 'ENABLED',
                                     'type': 'PRIMARY'}]})

        self.treq.json_content.assert_called_once_with(mock.ANY)

        self.log.msg.assert_called_with(
            'Added to load balancer', loadbalancer_id=12345,
            ip_address='192.168.1.1', node_id=1)

    def test_retries(self):
        """
        :func:`add_to_clb` will retry until it succeeds.
        """
        self.codes = [422] * 10 + [200]
        self.treq.post.side_effect = lambda *_, **ka: succeed(mock.Mock(code=self.codes.pop(0)))

        d = self._add_to_clb()
        self.clock.pump([self.retry_interval] * 11)
        result = self.successResultOf(d)
        self.assertEqual(result, self.json_content)
        self.assertEqual(
            self.treq.post.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes',
                       headers=expected_headers(self.auth_token),
                       data=mock.ANY,
                       log=matches(IsInstance(self.log.__class__)))] * 11)
        self.rand_interval.assert_called_once_with(5, 7)

    def test_stop_retrying_on_404(self):
        """
        :func:`add_to_clb` will stop retrying if it encounters a 404.
        """
        codes = iter([422, 422, 404])
        self.treq.post.side_effect = lambda *_, **ka: succeed(mock.Mock(code=next(codes)))

        d = self._add_to_clb()
        self.clock.advance(self.retry_interval)
        self.assertNoResult(d)

        self.clock.advance(self.retry_interval)
        f = self.failureResultOf(d, CLBOrNodeDeleted)
        self.assertEqual(f.value.clb_id, 12345)

    def test_stop_retrying_on_422_deleted_clb(self):
        """
        :func:`add_to_clb` will stop retrying if it encounters 422 with deleted CLB.
        """
        codes = iter([422, 422, 422])
        self.treq.post.side_effect = lambda *_, **ka: succeed(mock.Mock(code=next(codes)))
        messages = iter(['bad', 'huh', 'The load balancer is deleted'])
        self.treq.content.side_effect = lambda *a: succeed(
            json.dumps({"message": next(messages)}))

        d = self._add_to_clb()
        self.clock.advance(self.retry_interval)
        self.assertNoResult(d)

        self.clock.advance(self.retry_interval)
        f = self.failureResultOf(d, CLBOrNodeDeleted)
        self.assertEqual(f.value.clb_id, 12345)

    def test_defaults_retry_config(self):
        """
        :func:`add_to_clb` will use default :obj:`LB_RETRY_INTERVAL_RANGE`,
        :obj:`LB_MAX_RETRIES` values unless overridden.
        """
        set_config_data(fake_config)
        self.treq.post.side_effect = lambda *a, **kw: succeed(mock.Mock(code=422))

        d = self._add_to_clb()
        self.clock.pump([self.retry_interval] * LB_MAX_RETRIES)
        self.failureResultOf(d, RequestError)
        self.assertEqual(
            self.treq.post.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes',
                       headers=expected_headers(self.auth_token),
                       data=mock.ANY,
                       log=matches(IsInstance(self.log.__class__)))] *
            (LB_MAX_RETRIES + 1))
        self.rand_interval.assert_called_once_with(*LB_RETRY_INTERVAL_RANGE)

    def failed_add_to_clb(self, code=500):
        """
        Helper function to ensure :func:`add_to_clb` fails by returning
        failure again and again until it times out.
        """
        self.treq.post.side_effect = lambda *a, **kw: succeed(mock.Mock(code=code))
        d = self._add_to_clb()
        self.clock.pump([self.retry_interval] * self.max_retries)
        return d

    def test_retries_time_out(self):
        """
        :func:`add_to_clb` will retry up to ``worker.lb_max_retries`` times.
        It will fail after that. This also checks that API failure is propagated.
        """
        d = self.failed_add_to_clb(422)

        f = self.failureResultOf(d, RequestError)
        self.assertEqual(f.value.reason.value.code, 422)
        self.assertEqual(
            self.treq.post.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes',
                       headers=expected_headers(self.auth_token),
                       data=mock.ANY,
                       log=matches(IsInstance(self.log.__class__)))] *
            (self.max_retries + 1))

    def test_retries_log_unexpected_failure(self):
        """
        :func:`add_to_clb` will log all unexpected failures while (re)trying.
        This includes any failure besides a 422 with the ``PENDING_UPDATE``
        error message.
        """
        codes = iter([500, 503, 422, 422, 401, 200])
        self.treq.post.side_effect = lambda *_, **ka: succeed(mock.Mock(code=next(codes)))
        messages = iter(['bad'] * 3 + ['PENDING_UPDATE'] + ['hmm'])
        self.treq.content.side_effect = lambda *a: succeed(
            json.dumps({"message": next(messages)}))
        bad_codes = [500, 503, 422, 401]

        d = self._add_to_clb()
        self.clock.pump([self.retry_interval] * 6)
        self.successResultOf(d)
        self.assertEqual(
            self.log.msg.mock_calls[:len(bad_codes)],
            [mock.call(
                'Got unexpected LB status {status_code} while {msg}: {error}',
                status_code=bad_code, loadbalancer_id=12345,
                ip_address='192.168.1.1', msg='add_node',
                error=matches(IsInstance(APIError)))
             for bad_code in bad_codes])

    def test_pushes_remove_onto_undo_stack(self):
        """
        :func:`add_to_clb` pushes an inverse :func:`_remove_from_clb`
        operation onto the undo stack.
        """
        d = self._add_to_clb()
        self.successResultOf(d)
        self.undo.push.assert_called_once_with(
            _remove_from_clb, matches(IsInstance(self.log.__class__)),
            'http://dfw.lbaas/', self.auth_token,
            self.lb_config["loadBalancerId"], 1)

    def test_doesnt_push_onto_undo_stack_on_failure(self):
        """
        add_to_clb doesn't push an operation onto the undo stack
        if it fails.
        """
        d = self.failed_add_to_clb()
        self.failureResultOf(d, RequestError)
        self.assertFalse(self.undo.push.called)


class AddToLoadBalancerTests(LoadBalancersTestsMixin, SynchronousTestCase):
    """
    Tests for :func:`add_to_load_balancer`.

    This is really just a dispatch function towards specialized
    implementations. This tests that dispatching behavior.
    """

    def setUp(self):
        """
        Set up :class:`AddToLoadBalancerTests`.
        """
        super(AddToLoadBalancerTests, self).setUp()
        self.auth_token = self.request_bag.auth_token
        self.lb_config = None
        self.patch(launch_server_v1, "add_to_rcv3", self._fake_add_to_rcv3)
        self.patch(launch_server_v1, "add_to_clb", self._fake_add_to_clb)

    def _fake_add_to_rcv3(self, request_func, lb_id, server_id):
        """
        A test double for :func:`add_to_rcv3`.
        """
        self.assertIdentical(request_func, self.request_bag)
        self.assertEqual(lb_id, self.lb_config["loadBalancerId"])
        self.assertEqual(server_id, self.server_details["server"]["id"])
        rcv3_add_response = _rcv3_add_response_body(lb_id, server_id)
        return succeed(rcv3_add_response)

    def _fake_add_to_clb(self, log, endpoint, auth_token, lb_config,
                         ip_address, undo, clock):
        """
        A test double for :func:`add_to_clb`.
        """
        self.assertEqual(log, self.log)
        self.assertEqual(endpoint, 'http://dfw.lbaas/')
        self.assertEqual(auth_token, self.auth_token)
        self.assertEqual(ip_address, "10.0.0.1")
        self.assertEqual(undo, self.undo)
        self.assertEqual(clock, self.clock)
        self.assertEqual(lb_config, self.lb_config)
        return succeed(lb_response_1)

    def _add_to_load_balancer(self, lb_config):
        """
        Test for :func:`add_to_load_balancer`.

        Synchronously gets the deferred's result.
        """
        self.lb_config = lb_config
        d = add_to_load_balancer(self.log, self.request_bag,
                                 self.lb_config, self.server_details,
                                 self.undo, self.clock)
        return self.successResultOf(d)

    def test_implicit_clb(self):
        """
        When given an implicit CLB config (i.e. without explicit type) to
        add to, :func:`add_to_clb` is called.
        """
        self.assertEqual(self._add_to_load_balancer(lb_config_1), lb_response_1)

    def test_explicit_clb(self):
        """
        When given an explicit CLB config (i.e. with explicit
        ``CloudLoadBalancer`` type) to add to, :func:`add_to_clb` is called.
        """
        lb_config = dict(type="CloudLoadBalancer", **lb_config_1)
        self.assertEqual(self._add_to_load_balancer(lb_config), lb_response_1)

    def test_rcv3(self):
        """
        When given an RCv3 config to add to, :func:`add_to_rcv3` is called.
        """
        lb_config = {"type": "RackConnectV3", "loadBalancerId": "my-rcv3-lb-id"}
        response = self._add_to_load_balancer(lb_config)
        self.assertEqual(response[0]["status"], "ADDING")
        self.assertEqual(response[0]["load_balancer_pool"]["id"], "my-rcv3-lb-id")
        self.assertEqual(response[0]["cloud_server"]["id"], "my-server-id")

    def test_unknown_type(self):
        """
        :func:`add_to_load_balancer` synchronously raises an exception when
        given an unknown load balancer type.
        """
        bogus_lb_config = {"type": "TOTALLY BOGUS LB TYPE",
                           "transmogrification": "quantum"}
        self.assertRaises(RuntimeError,
                          self._add_to_load_balancer, bogus_lb_config)


class AddToLoadBalancersTests(LoadBalancersTestsMixin, SynchronousTestCase):
    """
    Tests for :func:`add_to_load_balancers`.
    """

    def _add_to_load_balancers(self, lb_configs):
        """
        Helper function to call :func:`add_to_load_balancers`.
        """
        return add_to_load_balancers(self.log, self.request_bag, lb_configs,
                                     self.server_details, self.undo)

    def _set_up_fake_add_to_lb(self, responses):
        """
        Creates a fake :func:`add_to_load_balancer` and sets up a patch for
        it. The patch will be automatically cleaned up at the end of the test.

        The fake will check that the arguments it is called with are
        correct, and then return a response from the given list.

        :param responses: Iterable of 2-tuples of ``lb_config`` and the desired
            responses, which should be deferreds.
        :return: :data:`None`
        """
        self._added_lbs = []
        self._fake_add_to_lb_responses = responses
        self.patch(launch_server_v1, "add_to_load_balancer", self._fake_add_to_lb)

    def _fake_add_to_lb(self, log, request_func, lb_config, server_details, undo):
        """
        Assert that func:`add_to_load_balancer` is being called with the
        right arguments, and returns an appropriate response.
        """
        self.assertEqual(log, self.log)
        self.assertEqual(request_func, self.request_bag)
        self.assertEqual(server_details, self.server_details)
        self.assertEqual(undo, self.undo)
        for (lb, response) in self._fake_add_to_lb_responses:
            if lb == lb_config:
                self._added_lbs.append(lb)
                return response
        raise RuntimeError("Unknown lb_config: {}!".format(lb_config))

    def test_add_to_load_balancers(self):
        """
        Add to load balancers will call add_to_clb multiple times and
        for each load balancer configuration and return all of the results.
        """
        self._set_up_fake_add_to_lb([
            (lb_config_1, succeed(lb_response_1)),
            (lb_config_2, succeed(lb_response_2))
        ])

        d = self._add_to_load_balancers([lb_config_1, lb_config_2])
        results = self.successResultOf(d)

        self.assertEqual(sorted(results), [(lb_config_1, lb_response_1),
                                           (lb_config_2, lb_response_2)])

    def test_serial_execution(self):
        """
        :func:`add_to_load_balancers` calls :func:`add_to_load_balancer`
        serially.
        """
        d1, d2 = Deferred(), Deferred()
        self._set_up_fake_add_to_lb([(lb_config_1, d1), (lb_config_2, d2)])

        d = self._add_to_load_balancers([lb_config_1, lb_config_2])

        # No result, still waiting on d1:
        self.assertNoResult(d)
        self.assertEqual(self._added_lbs, [lb_config_1])

        # d1 fires; still no result, waiting on d2:
        d1.callback(lb_response_1)
        self.assertNoResult(d)
        self.assertEqual(self._added_lbs, [lb_config_1, lb_config_2])

        # d2 fires, resulting cb fires too:
        d2.callback(lb_response_2)
        self.successResultOf(d)

    def test_no_lb_configs(self):
        """
        :func:`add_to_load_balancers` returns a Deferred that fires with an
        empty list when no load balancers are configured.
        """
        d = self._add_to_load_balancers([])
        self.assertEqual(self.successResultOf(d), [])

    def test_bail_on_errors(self):
        """
        When one of the underlying :func:`add_to_load_balancer` calls made by
        :func:`add_to_load_balancers` fails, the error is returned, and no
        further calls are made.
        """
        d1, d2, = Deferred(), Deferred()
        self._set_up_fake_add_to_lb([(lb_config_1, d1), (lb_config_2, d2)])

        d = self._add_to_load_balancers([lb_config_1, lb_config_2])
        self.assertNoResult(d)
        self.assertEqual(self._added_lbs, [lb_config_1])

        d1.errback(RuntimeError("welp!"))
        self.failureResultOf(d)

        self.assertEqual(self._added_lbs, [lb_config_1])


class RemoveFromCLBTests(LoadBalancersTestsMixin, SynchronousTestCase):
    """
    Tests for removing nodes from CLB load balancers, through the generic
    :func:`remove_from_load_balancer` API.
    """

    def setUp(self):
        """
        Mock :func:`treq.delete` for deleting nodes and set up a :class:`Clock`
        for simulating the passage of time for the retry tests.
        """
        super(RemoveFromCLBTests, self).setUp()
        self.treq = patch(self, 'otter.worker.launch_server_v1.treq',
                          new=mock_treq(code=200, content='{"message": "bad"}', method='delete'))
        patch(self, 'otter.util.http.treq', new=self.treq)
        self.clock = Clock()

    def _remove_from_load_balancer(self):
        """
        Helper function to call :func:`remove_from_load_balancer`.

        This will call it with a CLB load balancer configuration, and a CLB
        load balancer response.
        """
        d = remove_from_load_balancer(
            self.log, self.request_bag, lb_config_1, lb_response_1,
            clock=self.clock)
        return d

    def test_remove_from_load_balancer(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node.
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=200))
        self.treq.content.return_value = succeed('')

        d = self._remove_from_load_balancer()

        self.assertEqual(self.successResultOf(d), None)
        self.treq.delete.assert_called_once_with(
            'http://dfw.lbaas/loadbalancers/12345/nodes/a',
            headers=expected_headers(self.request_bag.auth_token),
            log=matches(IsInstance(self.log.__class__)))

    def test_remove_from_load_balancer_on_404(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node and ignores if it is already deleted
        i.e. it returns 404.
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=404))
        self.treq.content.return_value = succeed(json.dumps({'message': 'LB does not exist'}))

        d = self._remove_from_load_balancer()

        self.assertEqual(self.successResultOf(d), None)

    def test_remove_from_load_balancer_on_422_LB_deleted(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node and ignores if the load balancer
        has been deleted and is considered immutable (a 422 response with a
        particular message). It also logs it
        """
        message = "The load balancer is deleted and considered immutable."
        body = {"message": message, "code": 422}
        mock_treq(code=422, content=json.dumps(body), method='delete', treq_mock=self.treq)

        d = self._remove_from_load_balancer()

        self.assertEqual(self.successResultOf(d), None)
        self.log.msg.assert_any_call(
            matches(StartsWith('CLB 12345 or node a deleted due to RequestError')),
            loadbalancer_id=12345, node_id="a")

    def test_remove_from_load_balancer_on_422_Pending_delete(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node and ignores if the load balancer
        is in PENDING_DELETE and is considered immutable (a 422 response with a
        particular message). It also logs it
        """
        message = ("Load Balancer '12345' has a status of 'PENDING_DELETE' and "
                   "is considered immutable.")
        body = {"message": message, "code": 422}
        mock_treq(code=422, content=json.dumps(body), method='delete', treq_mock=self.treq)

        d = self._remove_from_load_balancer()

        self.assertEqual(self.successResultOf(d), None)
        self.log.msg.assert_any_call(
            matches(StartsWith('CLB 12345 or node a deleted due to RequestError')),
            loadbalancer_id=12345, node_id="a")

    def test_remove_from_load_balancer_fails_on_422_LB_other(self):
        """
        remove_from_load_balancer makes a DELETE request against the
        URL represting the load balancer node and will fail if the 422 response
        is not a result of the LB being deleted.
        """
        body = {
            "message": ("Load Balancer '1' has a status of 'ERROR' and is "
                        "considered immutable."),
            "code": 422
        }
        mock_treq(code=422, content=json.dumps(body), method='delete', treq_mock=self.treq)

        d = self._remove_from_load_balancer()

        self.failureResultOf(d, RequestError)
        self.log.msg.assert_any_call(
            'Got LB error while {m}: {e}', m='remove_node', e=mock.ANY,
            loadbalancer_id=12345, node_id="a")

    test_remove_from_load_balancer_fails_on_422_LB_other.skip = 'Until we bail out early on ERROR'

    def test_removelb_retries(self):
        """
        remove_from_load_balancer will retry again until it succeeds and retry interval
        will be random number based on lb_retry_interval_range config value
        """
        self.codes = [422] * 7 + [500] * 3 + [200]
        self.treq.delete.side_effect = lambda *_, **ka: succeed(mock.Mock(code=self.codes.pop(0)))
        self.treq.content.side_effect = lambda *a, **ka: succeed(
            json.dumps({'message': 'PENDING_UPDATE'}))

        d = self._remove_from_load_balancer()

        self.clock.pump([self.retry_interval] * 11)
        self.assertIsNone(self.successResultOf(d))
        # delete calls made?
        self.assertEqual(
            self.treq.delete.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes/a',
                       headers=expected_headers(self.request_bag.auth_token),
                       log=matches(IsInstance(self.log.__class__)))] * 11)
        # Expected logs?
        self.assertEqual(self.log.msg.mock_calls[0],
                         mock.call('Removing from load balancer',
                                   loadbalancer_id=12345, node_id="a"))
        self.assertEqual(self.log.msg.mock_calls[-1],
                         mock.call('Removed from load balancer',
                                   loadbalancer_id=12345, node_id="a"))
        # Random interval from config
        self.rand_interval.assert_called_once_with(5, 7)
        self.interval_func.assert_has_calls([mock.call(CheckFailure(RequestError))] * 10)

    def test_removelb_limits_retries(self):
        """
        remove_from_load_balancer will retry again and again for LB_MAX_RETRIES times.
        It will fail after that
        """
        self.treq.delete.side_effect = lambda *_, **ka: succeed(mock.Mock(code=422))
        self.treq.content.side_effect = lambda *a, **ka: succeed(
            json.dumps({'message': 'PENDING_UPDATE'}))

        d = self._remove_from_load_balancer()

        self.clock.pump([self.retry_interval] * self.max_retries)
        # failed?
        failure = self.failureResultOf(d, RequestError)
        self.assertEqual(failure.value.reason.value.code, 422)
        # delete calls made?
        self.assertEqual(
            self.treq.delete.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes/a',
                       headers=expected_headers(self.request_bag.auth_token),
                       log=matches(IsInstance(self.log.__class__)))] *
            (self.max_retries + 1))
        # Expected logs?
        self.assertEqual(self.log.msg.mock_calls[0],
                         mock.call('Removing from load balancer',
                                   loadbalancer_id=12345, node_id="a"))
        # Interval func call max times?
        self.rand_interval.assert_called_once_with(5, 7)
        self.interval_func.assert_has_calls(
            [mock.call(CheckFailure(RequestError))] * self.max_retries)

    def test_removelb_retries_uses_defaults(self):
        """
        remove_from_load_balancer will retry based on default config if lb_max_retries
        or lb_retry_interval_range is not found
        """
        set_config_data(fake_config)
        self.treq.delete.side_effect = lambda *_, **ka: succeed(mock.Mock(code=422))
        self.treq.content.side_effect = lambda *a, **ka: succeed(
            json.dumps({'message': 'PENDING_UPDATE'}))

        d = self._remove_from_load_balancer()

        self.clock.pump([self.retry_interval] * LB_MAX_RETRIES)
        # failed?
        failure = self.failureResultOf(d, RequestError)
        self.assertEqual(failure.value.reason.value.code, 422)
        # delete calls made?
        self.assertEqual(
            self.treq.delete.mock_calls,
            [mock.call('http://dfw.lbaas/loadbalancers/12345/nodes/a',
                       headers=expected_headers(self.request_bag.auth_token),
                       log=matches(IsInstance(self.log.__class__)))] *
            (LB_MAX_RETRIES + 1))
        # Expected logs?
        self.assertEqual(self.log.msg.mock_calls[0],
                         mock.call('Removing from load balancer',
                                   loadbalancer_id=12345, node_id="a"))
        # Interval func call max times?
        self.rand_interval.assert_called_once_with(*LB_RETRY_INTERVAL_RANGE)
        self.interval_func.assert_has_calls(
            [mock.call(CheckFailure(RequestError))] * LB_MAX_RETRIES)

    def test_removelb_retries_logs_unexpected_errors(self):
        """
        add_to_clb will log unexpeted failures while it is trying
        """
        self.codes = [500, 503, 422, 422, 401, 200]
        bad_codes = [500, 503, 401]
        self.treq.delete.side_effect = lambda *_, **ka: succeed(mock.Mock(code=self.codes.pop(0)))
        self.treq.content.side_effect = lambda *a, **ka: succeed(
            json.dumps({'message': 'PENDING_UPDATE'}))

        d = self._remove_from_load_balancer()

        self.clock.pump([self.retry_interval] * 6)
        self.successResultOf(d)
        self.log.msg.assert_has_calls(
            [mock.call(
                'Got unexpected LB status {status_code} while {msg}: {error}',
                status_code=code, msg='remove_node',
                error=matches(IsInstance(APIError)), loadbalancer_id=12345,
                node_id="a")
             for code in bad_codes])


class RemoveFromRCv3Tests(LoadBalancersTestsMixin, SynchronousTestCase):
    """
    Tests for removing nodes from RCv3 load balancers, through the generic
    :func:`remove_from_load_balancer` API.
    """

    def setUp(self):
        """
        Set up a test double for :func:`remove_from_rcv3`.
        """
        super(RemoveFromRCv3Tests, self).setUp()
        self.patch(launch_server_v1, "remove_from_rcv3",
                   self._fake_remove_from_rcv3)

    def _fake_remove_from_rcv3(self, request_func, lb_id, server_id):
        """
        A test double for :func`remove_from_rcv3`.

        Asserts that it was called appropriately, and then issues an
        appropriate response.

        :return: Deferred :data:`None`.

        """
        self.assertIdentical(request_func, self.request_bag)
        self.assertEqual(lb_id, "my-rcv3-lb-id")
        self.assertEqual(server_id, "my-server-id")
        return succeed(None)

    def test_remove_from_rcv3(self):
        """
        :func:`remove_from_load_balancer` correctly defers to
        :func:`remove_from_rcv3`.
        """
        lb_id = "my-rcv3-lb-id"
        rcv3_config = {"type": "RackConnectV3", "loadBalancerId": lb_id}
        rcv3_response = _rcv3_add_response_body(lb_id, "my-server-id")
        d = remove_from_load_balancer(self.log, self.request_bag,
                                      rcv3_config, rcv3_response)
        self.assertIdentical(self.successResultOf(d), None)


def _get_server_info(metadata=None, created=None):
    """
    Creates a fake server config to be used when testing creating servers
    (either as the config to use when creating, or as the config to return as
    a response).

    :param ``dict`` metadata: metadata to include in the server config
    :param ``created``: this is only used in server responses, but gives an
        extra field to distinguish one server config from another
    """
    config = {
        'name': 'abcd',
        'imageRef': '123',
        'flavorRef': 'xyz',
        'metadata': metadata or {}
    }
    if created is not None:
        config['created'] = created
    return config


class ServerTests(RequestBagTestMixin, SynchronousTestCase):
    """
    Test server manipulation functions.
    """
    def setUp(self):
        """
        Set up test dependencies.
        """
        super(ServerTests, self).setUp()
        self.log = mock_log()
        self.clock = Clock()
        set_config_data(fake_config)
        self.addCleanup(set_config_data, {})

        self.treq = patch(self, 'otter.worker.launch_server_v1.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

        launch_server_v1._create_server_sem = None

        self.generate_server_name = patch(
            self,
            'otter.worker.launch_server_v1.generate_server_name')
        self.generate_server_name.return_value = 'as000000'

        self.scaling_group_uuid = '1111111-11111-11111-11111111'

        self.scaling_group = mock.Mock(uuid=self.scaling_group_uuid, tenant_id='1234')

        self.undo = iMock(IUndoStack)

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

    def test_server_details_on_404(self):
        """
        server_details will raise a :class:`ServerDeleted` error when it
        it gets a 404 back in the response
        """
        mock_treq(code=404, content='not found', method='get',
                  treq_mock=self.treq)

        d = server_details('http://url/', 'my-auth-token', 'serverId')
        self.failureResultOf(d, ServerDeleted)

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

    def test_find_server_tells_nova_to_filter_by_image_flavor_and_name(self):
        """
        :func:`find_server` makes a call to nova to list server details while
        filtering on the image id, flavor id, and exact name in the server
        config.
        """
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({"servers": []})

        find_server('http://url/', 'my-auth-token', _get_server_info())

        url = urlunsplit([
            'http', 'url', 'servers/detail',
            urlencode({"image": "123", "flavor": "xyz", "name": "^abcd$"}),
            None])

        self.treq.get.assert_called_once_with(
            url, headers=expected_headers(), log=mock.ANY)

    def _test_find_server_no_image_id(self, server_config):
        """
        The query arg for image should just be "image=", so the URL should look
        like "...?...&image=" or "...?...&image=&..."
        """
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({"servers": []})

        find_server('http://url/', 'my-auth-token', server_config)
        self.treq.get.assert_called_once_with(
            matches(MatchesRegex('.*\?(.+&)?image=(&.+)$')),
            headers=expected_headers(),
            log=mock.ANY)

    def test_find_server_filters_by_image_even_if_imageRef_is_empty(self):
        """
        The :func:`find_server` filters on the image id even if the image id
        is blank (in the case of boot from volume - the server details does
        not have any information about block device mapping, however).

        Searching for "image=" will find only servers with an empty image id.
        """
        server_config = _get_server_info()
        server_config['imageRef'] = ""
        self._test_find_server_no_image_id(server_config)

    def test_find_server_filters_by_image_even_if_imageRef_is_null(self):
        """
        The :func:`find_server` filters on the image id even if the image id
        is null (in the case of boot from volume - the server details does
        not have any information about block device mapping, however).

        Searching for "image=" will find only servers with an empty image id.
        """
        server_config = _get_server_info()
        server_config['imageRef'] = None
        self._test_find_server_no_image_id(server_config)

    def test_find_server_filters_by_image_even_if_imageRef_not_provided(self):
        """
        The :func:`find_server` filters on the image id even if the image id
        is not provided (in the case of boot from volume - the server details
        does not have any information about block device mapping, however).

        Searching for "image=" will find only servers with an empty image id.
        """
        server_config = _get_server_info()
        server_config.pop('imageRef')
        self._test_find_server_no_image_id(server_config)

    def test_find_server_regex_escapes_server_name(self):
        """
        :func:`find_server` when giving the exact name of the server,
        regex-escapes the name
        """
        server_config = _get_server_info()
        server_config['name'] = r"this.is[]regex\dangerous()*"

        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({"servers": []})

        find_server('http://url/', 'my-auth-token', server_config)

        url = urlunsplit([
            'http', 'url', 'servers/detail',
            urlencode({"image": "123", "flavor": "xyz",
                       "name": r"^this\.is\[\]regex\\dangerous\(\)\*$"}),
            None])

        self.treq.get.assert_called_once_with(
            url, headers=expected_headers(), log=mock.ANY)

    def test_find_server_propagates_api_errors(self):
        """
        :func:`find_server` propagates any errors from Nova
        """
        self.treq.get.return_value = succeed(mock.Mock(code=500))
        self.treq.content.return_value = succeed(error_body)

        d = find_server('http://url/', 'my-auth-token', _get_server_info())
        failure = self.failureResultOf(d, APIError)
        self.assertEqual(failure.value.code, 500)

    def test_find_server_returns_None_if_no_servers_from_nova(self):
        """
        :func:`find_server` will return None for servers if Nova returns no
        matching servers
        """
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({"servers": []})

        d = find_server('http://url/', 'my-auth-token', _get_server_info())
        self.assertIsNone(self.successResultOf(d))

    def test_find_server_raises_if_server_from_nova_has_wrong_metadata(self):
        """
        :func:`find_server` will fail if the server Nova returned does not have
        matching metadata
        """
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({
            'servers': [_get_server_info(metadata={'hello': 'there'})]
        })

        d = find_server('http://url/', 'my-auth-token', _get_server_info())
        self.failureResultOf(d, ServerCreationRetryError)

    def test_find_server_returns_match_from_nova(self):
        """
        :func:`find_server` will return a server returned from Nova if the
        metadata match.
        """
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed(
            {'servers': [_get_server_info(metadata={'hey': 'there'})]})

        d = find_server('http://url/', 'my-auth-token',
                        _get_server_info(metadata={'hey': 'there'}))

        self.assertEqual(
            self.successResultOf(d),
            {'server': _get_server_info(metadata={'hey': 'there'})})

    def test_find_server_raises_if_nova_returns_more_than_one_server(self):
        """
        :func:`find_server` will return a the first server returned from Nova
        whose metadata match.  It logs if there more than 1 server from Nova.
        """
        servers = [
            _get_server_info(created='2014-04-04T04:04:04Z'),
            _get_server_info(created='2014-04-04T04:04:05Z'),
        ]

        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({'servers': servers})

        d = find_server('http://url/', 'my-auth-token', _get_server_info(),
                        self.log)

        self.failureResultOf(d, ServerCreationRetryError)

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server(self, fs):
        """
        :func:`create_server` will perform a properly formed POST request to the
        server endpoint and return the decoded json content.  It will not
        attempt to find a server in Nova if the create request succeeds.
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {'some': 'stuff'}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(202, {})

        _treq = StubTreq([(req, resp)], [(resp, '{"server": "created"}')])

        d = create_server('http://url/', 'my-auth-token', {'some': 'stuff'},
                          _treq=_treq, clock=self.clock)

        result = self.successResultOf(d)
        self.assertEqual(result, {"server": "created"})
        self.assertFalse(fs.called)

    def test_create_server_limits(self):
        """
        create_server when called many times will post only 1 request at
        a time if configured with limit of 1
        """
        deferreds = [Deferred() for i in range(3)]
        post_ds = deferreds[:]
        self.treq.post.side_effect = lambda *a, **kw: deferreds.pop(0)

        server_config = {
            'name': 'someServer',
            'imageRef': '1',
            'flavorRef': '3'
        }
        set_config_data({"worker": {"create_server_limit": 1}})

        ret_ds = [create_server('http://url/', 'my-auth-token',
                                server_config, clock=self.clock)
                  for i in range(3)]

        # no result in any of them and only 1 treq.post is called
        for d in ret_ds:
            self.assertNoResult(d)
        self.assertEqual(self.treq.post.call_count, 1)

        # fire first deferred and notice that next treq.post is still not
        # called due to delay
        post_ds[0].callback(mock.Mock(code=202))
        self.assertEqual(self.treq.post.call_count, 1)

        # advance clock and notice next post called
        self.clock.advance(1)
        self.assertEqual(self.treq.post.call_count, 2)
        self.successResultOf(ret_ds[0])

        # fire others
        post_ds[1].callback(mock.Mock(code=202))
        self.clock.advance(1)
        post_ds[2].callback(mock.Mock(code=202))
        self.clock.advance(1)
        self.successResultOf(ret_ds[1])
        self.successResultOf(ret_ds[2])

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server_propagates_api_failure_from_create(self, fs):
        """
        :func:`create_server` will propagate API failures from the call to
        create the server, if :func:`find_server` also failed with an API
        failure.
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(500, {})

        _treq = StubTreq([(req, resp)], [(resp, 'failure')])

        fs.return_value = fail(APIError(401, '', {}))

        d = create_server(
            'http://url/', 'my-auth-token', {}, log=self.log, retries=0,
            _treq=_treq, create_failure_delay=5, clock=self.clock)
        self.clock.advance(5)

        failure = self.failureResultOf(d, RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)

        self.assertEqual(len(fs.mock_calls), 1)

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server_returns_found_server(self, fs):
        """
        If attempting to create a server fails due to a Nova error or identity
        error, but a server was indeed created and found, :func:`create_server`
        returns this found server successfully.  Creation is not retried.
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {'some': 'stuff'}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(500, {})

        _treq = StubTreq([(req, resp)], [(resp, 'failure')])

        fs.return_value = succeed("I'm a server!")

        d = create_server(
            'http://url/', 'my-auth-token', {'some': 'stuff'}, _treq=_treq,
            create_failure_delay=5, clock=self.clock)
        self.assertNoResult(d)

        self.clock.advance(5)

        result = self.successResultOf(d)
        self.assertEqual(result, "I'm a server!")

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server_errors_if_no_server_found(self, fs):
        """
        If attempting to create a server fails due to a Nova error or identity
        error, and a created server was not found, :func:`create_server`
        returns original error when on the last retry.
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(500, {})

        _treq = StubTreq([(req, resp)], [(resp, 'failure')])

        fs.return_value = succeed(None)

        d = create_server(
            'http://url/', 'my-auth-token', {}, log=self.log, retries=0,
            _treq=_treq, create_failure_delay=5, clock=self.clock)
        self.assertNoResult(d)
        self.clock.advance(5)

        failure = self.failureResultOf(d, RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)

        self.assertEqual(fs.mock_calls,
                         [mock.call('http://url/', 'my-auth-token', {},
                                    log=self.log)])

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server_retries_if_no_server_found(self, fs):
        """
        If attempting to create a server fails due to a Nova error or identity
        error, and no server was found to be created, :func:`create_server`
        reties the create up to 3 times by default
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(500, {})

        _treq = StubTreq([(req, resp)], [(resp, error_body)])

        fs.side_effect = lambda *a, **kw: succeed(None)

        d = create_server('http://url/', 'my-auth-token', {}, log=self.log,
                          _treq=_treq, create_failure_delay=5,
                          clock=self.clock)
        self.clock.pump([1, 5])

        for i in range(3):
            self.assertEqual(len(fs.mock_calls), i + 1)
            self.clock.pump([15, 1, 5])

        self.failureResultOf(d)
        self.assertEqual(len(fs.mock_calls), 4)

    @mock.patch('otter.worker.launch_server_v1.find_server')
    def test_create_server_does_not_retry_on_400_response(self, fs):
        """
        If attempting to create a server fails due to a Nova 400 error,
        creation is not retried.  Server existence is not attempted.
        """
        req = ('POST', 'http://url/servers',
               headers('my-auth-token'),
               json.dumps({'server': {}}),
               None,
               {'log': mock.ANY})
        resp = StubResponse(400, {})

        _treq = StubTreq([(req, resp)], [(resp, "User error!")])

        d = create_server(
            'http://url/', 'my-auth-token', {}, log=self.log, _treq=_treq)
        self.clock.advance(15)

        failure = self.failureResultOf(d, RequestError)
        self.assertTrue(failure.value.reason.check(APIError))
        real_failure = failure.value.reason
        self.assertEqual(real_failure.value.code, 400)
        self.assertFalse(fs.called)

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
                            interval=5, clock=clock)

        self.log.msg.assert_called_once_with(
            "Checking instance status every {interval} seconds", interval=5)

        server_details.assert_called_with('http://url/', 'my-auth-token',
                                          'serverId', log=mock.ANY)
        self.assertEqual(server_details.call_count, 1)

        server_status[0] = 'ACTIVE'

        clock.advance(5)

        server_details.assert_called_with('http://url/', 'my-auth-token',
                                          'serverId', log=mock.ANY)
        self.assertEqual(server_details.call_count, 2)

        self.log.msg.assert_called_with(
            "Server changed from 'BUILD' to 'ACTIVE' within {time_building} seconds",
            time_building=5.0)

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
                            interval=5, clock=clock)

        clock.advance(5)

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(UnexpectedServerStatus))

        self.log.msg.assert_called_with(
            "Server changed to '{status}' in {time_building} seconds",
            time_building=5.0, status='ERROR')

        self.assertEqual(failure.value.server_id, 'serverId')
        self.assertEqual(failure.value.status, 'ERROR')
        self.assertEqual(failure.value.expected_status, 'ACTIVE')

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_continues_looping_on_500(self, server_details):
        """
        wait_for_active will keep looping if ``server_details`` raises other
        exceptions, for instance RequestErrors.
        """
        clock = Clock()

        server_details.return_value = fail(
            RequestError(Failure(APIError(500, '', {})), 'url'))

        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            interval=5, clock=clock)

        self.assertNoResult(d)
        server_details.return_value = succeed({'server': {'status': 'ACTIVE'}})

        clock.advance(5)

        result = self.successResultOf(d)
        self.assertEqual(result['server']['status'], 'ACTIVE')

    @mock.patch('otter.worker.launch_server_v1.server_details')
    def test_wait_for_active_stops_looping_on_server_deletion(self, server_details):
        """
        wait_for_active will errback it's Deferred if ``server_details`` raises
        a ``ServerDeletion`` error
        """
        clock = Clock()

        server_details.return_value = fail(ServerDeleted('1234'))
        d = wait_for_active(self.log,
                            'http://url/', 'my-auth-token', 'serverId',
                            interval=5, clock=clock)

        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(ServerDeleted))

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
                            interval=5, clock=clock)

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
                            interval=5, clock=clock)

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
        self.failureResultOf(d, TimedOutError)

        # the loop has stopped
        clock.advance(5)
        self.assertEqual(server_details.call_count, 2)

    def test_wait_for_active_default_timeout(self):
        """:func`wait_for_active` waits for 2 hours by default."""
        self.assertEqual(defaults_by_name(wait_for_active)["timeout"],
                         2 * 60 * 60)

    def _launch_server(self, launch_config, log=None, clock=None):
        """
        Helper method for calling :func:`launch_server`.
        """
        d = launch_server(log if log is not None else self.log,
                          self.request_bag, self.scaling_group,
                          launch_config, self.undo, clock=clock)
        return d

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
                             {'loadBalancerId': 54321, 'port': 81}]}

        prepared_load_balancers = [
            {'loadBalancerId': 12345, 'port': 80},
            {'loadBalancerId': 54321, 'port': 81}
        ]

        expected_server_config = {
            'imageRef': '1', 'flavorRef': '1', 'name': 'as000000',
            'metadata': {
                'rax:auto_scaling_group_id': '1111111-11111-11111-11111111',
                'rax:autoscale:group:id': '1111111-11111-11111-11111111',
                'rax:autoscale:lb:CloudLoadBalancer:12345': '[{"port": 80}]',
                'rax:autoscale:lb:CloudLoadBalancer:54321': '[{"port": 81}]'
            }
        }

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_active.return_value = succeed(server_details)

        add_to_load_balancers.return_value = succeed([
            (lb_config_1, ('10.0.0.1', 80)),
            (lb_config_2, ('10.0.0.1', 81))
        ])

        log = mock.Mock()
        result = self.successResultOf(self._launch_server(launch_config, log))

        self.assertEqual(
            result,
            (server_details, [
                (lb_config_1, ('10.0.0.1', 80)),
                (lb_config_2, ('10.0.0.1', 81))]))

        # reauth should have been called, and the new request bag should be
        # used everywhere in place of the original
        self.assertEqual(len(self.bags), 1)
        create_server.assert_called_once_with('http://dfw.openstack/',
                                              self.bags[-1].auth_token,
                                              expected_server_config,
                                              log=mock.ANY)

        wait_for_active.assert_called_once_with(mock.ANY,
                                                'http://dfw.openstack/',
                                                self.bags[-1].auth_token,
                                                '1')

        log.bind.assert_called_once_with(server_name='as000000')
        log = log.bind.return_value
        log.bind.assert_called_once_with(server_id='1')
        add_to_load_balancers.assert_called_once_with(
            log.bind.return_value, self.bags[-1], prepared_load_balancers,
            {
                'server': {
                    'id': '1',
                    'addresses': {
                        'private': [{'version': 4, 'addr': '10.0.0.1'}]
                    }
                }
            },
            self.undo)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_doesnt_check_networks_if_no_load_balancers(
            self, wait_for_active, create_server, add_to_load_balancers):
        """
        :func:`launch_server` will succeed at launching a server that has no
        servicenet configured, so long as it also does not require load
        balancers
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'}}
        server_details = {
            'server': {
                'id': '1',
                'addresses': {'public': [{'version': 4, 'addr': '10.0.0.1'}]}
            }
        }

        create_server.return_value = succeed(server_details)
        wait_for_active.return_value = succeed(server_details)

        log = mock.Mock()
        result = self.successResultOf(self._launch_server(launch_config, log))

        self.assertEqual(result, (server_details, []))

        self.assertFalse(add_to_load_balancers.called)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_logs_if_metadata_does_not_match(
            self, wait_for_active, create_server, add_to_load_balancers):
        """
        :func:`launch_server` will succeed but log a message if a server's
            metadata has changed between server launch and server becoming
            active
        """
        launch_config = {
            'server': {'imageRef': '1', 'flavorRef': '1'},
            'loadBalancers': [{'loadBalancerId': 12345, 'port': 80}]
        }
        server_details = {
            'server': {
                'id': '1',
                'addresses': {'public': [{'version': 4, 'addr': '10.0.0.1'}],
                              'private': [{'version': 4, 'addr': '1.1.1.1'}]},
                'metadata': {'this': 'is invalid'}
            }
        }

        create_server.return_value = succeed(server_details)
        wait_for_active.return_value = succeed(server_details)

        d = self._launch_server(launch_config)
        expected_metadata = {
            "rax:auto_scaling_group_id": self.scaling_group.uuid,
            "rax:autoscale:group:id": self.scaling_group.uuid,
            "rax:autoscale:lb:CloudLoadBalancer:12345": '[{"port": 80}]'
        }

        self.successResultOf(d)
        self.assertEqual(
            self.log.msg.mock_calls,
            [mock.call('Server metadata has changed.',
                       sanity_check=True,
                       expected_metadata=expected_metadata,
                       nova_metadata={'this': 'is invalid'},
                       server_id=mock.ANY,
                       server_name=mock.ANY)])

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

        d = self._launch_server({'server': {}})
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

        d = self._launch_server(launch_config)
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
        launch_config = {
            'server': {'imageRef': '1', 'flavorRef': '1'},
            'loadBalancers': [{'loadBalancerId': 12345, 'port': 80}]
        }

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = succeed(server_details)

        wait_for_active.return_value = succeed(server_details)

        add_to_load_balancers.return_value = fail(
            APIError(500, "Oh noes")).addErrback(wrap_request_error, 'url')

        d = self._launch_server(launch_config)
        failure = self.failureResultOf(d)
        failure.trap(RequestError)
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, "Oh noes")

    @mock.patch('otter.worker.launch_server_v1.verified_delete')
    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_server_pushes_verified_delete_onto_undo(
            self, wait_for_active, create_server, add_to_load_balancers,
            verified_delete):
        """
        launch_server will push verified_delete onto the undo stack
        after the server is successfully created.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        create_server.return_value = Deferred()

        wait_for_active.return_value = succeed(server_details)

        mock_server_response = {'server': {'id': '1',
                                           'addresses': {'private': [{'version': 4,
                                                                      'addr': '10.0.0.1'}]}}}
        mock_lb_response = [(lb_config_1, ('10.0.0.1', 80)), (lb_config_2, ('10.0.0.1', 81))]
        add_to_load_balancers.return_value = succeed((mock_server_response, mock_lb_response))

        d = self._launch_server(launch_config)

        # Check that the push hasn't happened because create_server hasn't
        # succeeded yet.
        self.assertEqual(self.undo.push.call_count, 0)

        create_server.return_value.callback(server_details)

        self.successResultOf(d)

        self.assertEqual(len(self.bags), 1)
        self.undo.push.assert_called_once_with(
            verified_delete,
            mock.ANY,
            'http://dfw.openstack/',
            self.bags[-1],
            '1')

    @mock.patch('otter.worker.launch_server_v1.create_server')
    def test_launch_server_doesnt_push_undo_op_on_create_server_failure(
            self, create_server):
        """
        launch_server won't push anything onto the undo stack if create_server
        fails.
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': []}

        create_server.return_value = fail(APIError(500, ''))

        d = self._launch_server(launch_config)
        self.failureResultOf(d, APIError)
        self.assertEqual(self.undo.push.call_count, 0)

    @mock.patch('otter.worker.launch_server_v1.verified_delete')
    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_retries_on_error(self, mock_wfa, mock_cs, mock_addlb,
                                     mock_vd):
        """
        If server goes into ERROR state, launch_server deletes it and creates
        a new one instead
        """
        launch_config = {
            'server': {'imageRef': '1', 'flavorRef': '1'},
            'loadBalancers': [{'loadBalancerId': 12345, 'port': 80},
                              {'loadBalancerId': 54321, 'port': 81}]
        }

        metadata = {
            "rax:auto_scaling_group_id": self.scaling_group.uuid,
            "rax:autoscale:group:id": self.scaling_group.uuid,
            "rax:autoscale:lb:CloudLoadBalancer:12345": '[{"port": 80}]',
            "rax:autoscale:lb:CloudLoadBalancer:54321": '[{"port": 81}]'
        }

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]},
                'metadata': metadata
            }
        }

        mock_cs.side_effect = lambda *a, **kw: succeed(server_details)

        wfa_returns = [fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE')),
                       fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE')),
                       succeed(server_details)]
        mock_wfa.side_effect = lambda *a: wfa_returns.pop(0)
        mock_vd.side_effect = lambda *a: Deferred()

        clock = Clock()
        d = self._launch_server(launch_config, clock=clock)

        # No result, create_server and wait_for_active called once,
        # server deletion was started and it wasn't added to clb
        self.assertNoResult(d)
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(mock_cs.call_count, 1)
        self.assertEqual(mock_wfa.call_count, 1)
        mock_vd.assert_called_once_with(
            # the undo stack is not re-wound, so original request bag is used
            matches(IsInstance(self.log.__class__)), 'http://dfw.openstack/',
            self.request_bag, '1')
        self.log.msg.assert_called_once_with(
            '{server_id} errored, deleting and creating new server instead',
            server_name='as000000', server_id='1')

        self.assertFalse(mock_addlb.called)

        # After 15 seconds, server was created again, notice that verified_delete
        # incompletion doesn't hinder new server creation
        clock.advance(15)
        self.assertNoResult(d)
        self.assertEqual(len(self.bags), 2)
        self.assertEqual(mock_cs.call_count, 2)
        self.assertEqual(mock_wfa.call_count, 2)
        self.assertEqual(
            mock_vd.mock_calls,
            # the undo stack is not re-wound, so original request bag is used
            [mock.call(matches(IsInstance(self.log.__class__)),
                       'http://dfw.openstack/',
                       self.request_bag, '1')] * 2)
        self.assertEqual(
            self.log.msg.mock_calls,
            [mock.call('{server_id} errored, deleting and creating '
                       'new server instead',
                       server_name='as000000', server_id='1')] * 2)
        self.assertFalse(mock_addlb.called)

        # next time server creation succeeds
        clock.advance(15)
        self.successResultOf(d)
        self.assertEqual(len(self.bags), 3)  # reauthed a third time due
        self.assertEqual(mock_cs.call_count, 3)
        self.assertEqual(mock_wfa.call_count, 3)
        self.assertEqual(mock_vd.call_count, 2)
        self.assertEqual(self.log.msg.call_count, 2)
        self.assertEqual(mock_addlb.call_count, 1)

    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_no_retry_on_non_error(self, mock_wfa, mock_cs, mock_addlb):
        """
        launch_server does not retry to create server if server goes into any state
        other than ERROR
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': [
                             {'loadBalancerId': 12345, 'port': 80},
                             {'loadBalancerId': 54321, 'port': 81}
                         ]}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        mock_cs.side_effect = lambda *a, **kw: succeed(server_details)

        wfa_returns = [fail(UnexpectedServerStatus('1', 'SOME', 'ACTIVE')),
                       succeed(server_details)]
        mock_wfa.side_effect = lambda *a: wfa_returns.pop(0)

        clock = Clock()
        d = self._launch_server(launch_config, clock=clock)

        self.failureResultOf(d, UnexpectedServerStatus)
        self.assertEqual(mock_cs.call_count, 1)
        self.assertEqual(mock_wfa.call_count, 1)
        self.assertFalse(mock_addlb.called)

    @mock.patch('otter.worker.launch_server_v1.verified_delete')
    @mock.patch('otter.worker.launch_server_v1.add_to_load_balancers')
    @mock.patch('otter.worker.launch_server_v1.create_server')
    @mock.patch('otter.worker.launch_server_v1.wait_for_active')
    def test_launch_max_retries(self, mock_wfa, mock_cs, mock_addlb, mock_vd):
        """
        server is created again max 3 times if it goes into ERROR state
        """
        launch_config = {'server': {'imageRef': '1', 'flavorRef': '1'},
                         'loadBalancers': [
                             {'loadBalancerId': 12345, 'port': 80},
                             {'loadBalancerId': 54321, 'port': 81}
                         ]}

        server_details = {
            'server': {
                'id': '1',
                'addresses': {'private': [
                    {'version': 4, 'addr': '10.0.0.1'}]}}}

        mock_cs.side_effect = lambda *a, **kw: succeed(server_details)

        wfa_returns = [fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE')),
                       fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE')),
                       fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE')),
                       fail(UnexpectedServerStatus('1', 'ERROR', 'ACTIVE'))]
        mock_wfa.side_effect = lambda *a: wfa_returns.pop(0)

        clock = Clock()
        d = self._launch_server(launch_config, clock=clock)

        clock.pump([15] * 3)
        self.failureResultOf(d, UnexpectedServerStatus)
        self.assertEqual(mock_cs.call_count, 4)
        self.assertEqual(mock_wfa.call_count, 4)
        self.assertEqual(mock_vd.call_count, 3)
        self.assertFalse(mock_addlb.called)


class ConfigPreparationTests(SynchronousTestCase):
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
        expected_name = 'web.example.com-as000000'

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
        test_config = {'server': {},
                       "loadBalancers": [{'loadBalancerId': 1, 'port': 80},
                                         {'loadBalancerId': 2, 'port': 2200}]}
        expected_metadata = {
            'rax:auto_scaling_group_id': self.scaling_group_uuid,
            'rax:autoscale:group:id': self.scaling_group_uuid,
            'rax:autoscale:lb:CloudLoadBalancer:1': '[{"port": 80}]',
            'rax:autoscale:lb:CloudLoadBalancer:2': '[{"port": 2200}]'
        }

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
            'rax:autoscale:group:id': self.scaling_group_uuid,
            'foo': 'bar'}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertEqual(expected_metadata,
                         launch_config['server']['metadata'])

    def test_launch_config_is_copy(self):
        """
        The input launch config is not mutated by prepare_launch_config.
        """
        test_config = {'server': {}}

        launch_config = prepare_launch_config(self.scaling_group_uuid,
                                              test_config)

        self.assertNotIdentical(test_config, launch_config)


sample_launch_config = {
    'server': {
        'imageRef': '1',
        'flavorRef': '1'
    },
    'loadBalancers': [
        {'loadBalancerId': 12345, 'port': 80},
        {'loadBalancerId': 54321, 'port': 81}
    ]
}

sample_otter_metadata = {
    "rax:auto_scaling_group_id": "group_id",
    "rax:autoscale:group:id": "group_id",
    "rax:autoscale:lb:CloudLoadBalancer:12345": '[{"port": 80}]',
    "rax:autoscale:lb:CloudLoadBalancer:54321": '[{"port": 81}]'
}

sample_user_metadata = {"some_user_key": "some_user_value"}


class MetadataScrubbingTests(SynchronousTestCase):
    """
    Tests for scrubbing of metadata.
    """
    def test_without_otter_metadata(self):
        """
        :func:`_without_otter_metadata` correctly removes otter-specific
        keys and correctly keeps other keys.
        """
        samples = [
            ({'metadata': {}}, {'metadata': {}}),
            ({'metadata': sample_otter_metadata}, {'metadata': {}}),
            ({'metadata': merge(sample_otter_metadata, sample_user_metadata)},
             {'metadata': sample_user_metadata})
        ]

        for metadata, expected_scrubbed_metadata in samples:
            scrubbed = _without_otter_metadata(metadata)
            self.assertEqual(scrubbed, expected_scrubbed_metadata)

    def test_scrub_otter_metadata(self):
        """
        Scrubbing otter metadata works correctly.
        """
        set_config_data(fake_config)
        self.addCleanup(set_config_data, {})

        log = mock.Mock()

        expected_url = 'http://ord.openstack/servers/server/metadata'
        treq = StubTreq2([(("GET", expected_url,
                            {"headers": expected_headers(),
                             "data": None}),
                           (200, json.dumps({
                               'metadata': merge(sample_otter_metadata,
                                                 sample_user_metadata)}))),
                          (("PUT", expected_url,
                            {"headers": expected_headers(),
                             "data": json.dumps({
                                 'metadata': sample_user_metadata})}),
                           (200, ""))])

        d = scrub_otter_metadata(log=log,
                                 auth_token="my-auth-token",
                                 service_catalog=fake_service_catalog,
                                 region="ORD",
                                 server_id="server",
                                 _treq=treq)

        body = self.successResultOf(d)
        self.assertEqual(body, "")


# An instance associated with a single load balancer.
old_style_instance_details = (
    'a',
    [(12345, {'nodes': [{'id': 1}]}),
     (54321, {'nodes': [{'id': 2}]})])
instance_details = _as_new_style_instance_details(old_style_instance_details)


class DeleteServerTests(RequestBagTestMixin, SynchronousTestCase):
    """
    Test the delete server worker.
    """
    def setUp(self):
        """
        Set up some mocks.
        """
        super(DeleteServerTests, self).setUp()

        set_config_data(fake_config)
        self.addCleanup(set_config_data, {})

        self.log = mock_log()
        self.treq = patch(self, 'otter.worker.launch_server_v1.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

        self.treq.delete.return_value = succeed(mock.Mock(code=404))
        self.treq.content.side_effect = lambda *a, **kw: succeed("")

        self.remove_from_load_balancer = patch(
            self, 'otter.worker.launch_server_v1.remove_from_load_balancer')
        self.remove_from_load_balancer.return_value = succeed(None)

        self.clock = Clock()
        self.url = 'http://url'
        self.server_id = 'serverId'

    def _delete_server(self, instance_details):
        """
        Helper method to call :func:`delete_server`.
        """
        d = delete_server(self.log, self.request_bag, instance_details,
                          clock=self.clock)
        self.clock.advance(0.4)
        return d

    def test_delete_server_no_lbs(self):
        """
        :func:`delete_server` removes the nodes specified in instance details
        when there are no associated load balancers
        """
        self.successResultOf(self._delete_server(instance_details=('a', [])))
        self.assertFalse(self.remove_from_load_balancer.called)

    def _test_delete_server_lb_removal(self, instance_details):
        """
        Helper test to verify that :func:`delete_server` removes the nodes
        specified in instance details from the associated load balancers.
        """
        self.successResultOf(self._delete_server(instance_details))

        lb_details = _as_new_style_instance_details(instance_details)[1]
        expected_calls = [mock.call(self.log, self.request_bag,
                                    lb_config, lb_response)
                          for (lb_config, lb_response) in lb_details]
        self.remove_from_load_balancer.assert_has_calls(expected_calls,
                                                        any_order=True)
        self.assertEqual(self.remove_from_load_balancer.call_count, 2)

    def test_delete_servers_lb_removal_old_style(self):
        """
        :func:`delete_server` removes the nodes specified in instance details
        from the associated load balancers, even when ``instance_details`` is
        old-style.
        """
        self._test_delete_server_lb_removal(old_style_instance_details)

    def test_delete_servers_lb_removal(self):
        """
        :func:`delete_server` removes the nodes specified in instance details
        from the associated load balancers.
        """
        self._test_delete_server_lb_removal(instance_details)

    def _test_delete_server(self, instance_details):
        """
        Helper test to verify that :func:`delete_server` performs a
        ``DELETE`` request against the instance URL based on the
        information in ``instance_details``.
        """
        self.successResultOf(self._delete_server(instance_details))
        self.assertEqual(len(self.bags), 1)  # verified delete re-auths
        self.treq.delete.assert_called_once_with(
            'http://dfw.openstack/servers/a',
            headers=expected_headers(self.bags[-1].auth_token),
            log=mock.ANY)

    def test_delete_server_old_style(self):
        """
        :func:`delete_server` performs a ``DELETE`` request against the
        instance URL based on the information in ``instance_details``,
        even when ``instance_details`` is old-style.
        """
        self._test_delete_server(old_style_instance_details)

    def test_delete_server(self):
        """
        :func:`delete_server` performs a ``DELETE`` request against the
        instance URL based on the information in ``instance_details``.
        """
        self._test_delete_server(instance_details)

    def _test_delete_server_succeeds_on_unknown_server(self, instance_details):
        """
        Helper test to check if :func:`delete_server` succeeds and logs if
        delete calls return 404.
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=404))
        self.successResultOf(self._delete_server(instance_details))

    def test_delete_server_succeeds_on_unknown_server_old_style(self):
        """
        :func:`delete_server` succeeds and logs if delete calls return
        404, even if the ``instance`` details are old-style.
        """
        self._test_delete_server_succeeds_on_unknown_server(
            old_style_instance_details)

    def test_delete_server_succeeds_on_unknown_server(self):
        """
        :func:`delete_server` succeeds and logs if delete calls return
        404.
        """
        self._test_delete_server_succeeds_on_unknown_server(
            instance_details)

    def _test_delete_server_propagates_loadbalancer_failures(
            self, instance_details):
        """
        :func:`delete_server` propagates any errors that occur when
        removing server from load balancers.
        """
        self.remove_from_load_balancer.return_value = fail(
            APIError(500, '')).addErrback(wrap_request_error, 'url')

        d = self._delete_server(instance_details)
        failure = unwrap_first_error(self.failureResultOf(d))

        self.assertEqual(failure.value.reason.value.code, 500)

    def test_delete_server_propagates_loadbalancer_failures_old_style(self):
        """
        :func:`delete_server` propagates any errors that occur when
        removing server from load balancers, even if the ``instance``
        details are old-style.
        """
        self._test_delete_server_propagates_loadbalancer_failures(
            old_style_instance_details)

    def test_delete_server_propagates_loadbalancer_failures(self):
        """
        :func:`delete_server` propagates any errors that occur when
        removing server from load balancers.
        """
        self._test_delete_server_propagates_loadbalancer_failures(
            instance_details)

    @mock.patch('otter.worker.launch_server_v1.verified_delete')
    def _test_delete_server_propagates_verified_delete_failures(
            self, instance_details, deleter):
        """
        Helper function to verify that :func:`delete_server` fails with an
        :exc:`APIError` if deleting the server fails.
        """
        deleter.return_value = fail(TimedOutError(3660, 'meh'))

        d = self._delete_server(instance_details)
        self.failureResultOf(d, TimedOutError)

    def test_delete_server_propagates_verified_delete_failures_old_style(self):
        """
        :func:`delete_server` fails with an :exc:`APIError` if deleting
        the server fails, even if the ``instance`` details are old-style.
        """
        self._test_delete_server_propagates_verified_delete_failures(
            instance_details)

    def test_delete_server_propagates_verified_delete_failures(self):
        """
        :func:`delete_server` fails with an :exc:`APIError` if deleting
        the server fails.
        """
        self._test_delete_server_propagates_verified_delete_failures(
            instance_details)

    def _delete_and_verify(self):
        d = delete_and_verify(self.log, self.url, self.request_bag,
                              self.server_id, self.clock)
        self.clock.advance(0.4)
        return d

    def test_delete_and_verify_does_not_verify_if_404(self):
        """
        :func:`delete_and_verify` does not verify if the deletion response
        code is a 404.
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=404))
        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 0)
        self.successResultOf(d)

    def test_delete_and_verify_succeeds_if_get_returns_404(self):
        """
        :func:`delete_and_verify` succeeds if the verification response code
        is a 404
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=204))
        self.treq.get.return_value = succeed(mock.Mock(code=404))

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 1)
        self.successResultOf(d)

    def test_delete_and_verify_limits(self):
        """
        :func:`delete_and_verify` limits the number of delete server requests
        to 1. It also delays response by 1 second
        """
        deferreds = [Deferred() for i in range(3)]
        delete_ds = deferreds[:]
        self.treq.delete.side_effect = lambda *a, **kw: deferreds.pop(0)

        ret_ds = [delete_and_verify(self.log, 'http://url/',
                                    self.request_bag, 'serverId', self.clock)
                  for i in range(3)]

        # no result in any of them and only 1 treq.delete is called
        for d in ret_ds:
            self.assertNoResult(d)
        self.assertEqual(self.treq.delete.call_count, 1)

        # fire first deferred and notice that next treq.delete is still not
        # called due to delay
        delete_ds[0].callback(mock.Mock(code=404))
        self.assertEqual(self.treq.delete.call_count, 1)

        # advance clock and notice next delete called
        self.clock.advance(1)
        self.assertEqual(self.treq.delete.call_count, 2)
        self.successResultOf(ret_ds[0])
        self.assertNoResult(ret_ds[1])
        self.assertNoResult(ret_ds[2])

        # fire others
        delete_ds[1].callback(mock.Mock(code=404))
        self.clock.advance(1)
        delete_ds[2].callback(mock.Mock(code=404))
        self.clock.advance(1)
        self.successResultOf(ret_ds[1])
        self.successResultOf(ret_ds[2])

    def test_delete_and_verify_succeeds_if_task_state_is_deleting(self):
        """
        :func:`delete_and_verify` succeeds if the verification response body
        has a task_state of "deleting"
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=204))
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed(
            {'server': {'OS-EXT-STS:task_state': 'deleting'}})

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 1)
        self.successResultOf(d)

    def test_delete_and_verify_fails_if_task_state_not_deleting(self):
        """
        :func:`delete_and_verify` fails if the verification response body
        has a task_state that is not "deleting"
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=204))
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed(
            {'server': {'OS-EXT-STS:task_state': 'build'}})

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 1)
        self.failureResultOf(d, UnexpectedServerStatus)

    def test_delete_and_verify_fails_if_no_task_state(self):
        """
        :func:`delete_and_verify` fails if the verification response body
        does not have a task_state
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=204))
        self.treq.get.return_value = succeed(mock.Mock(code=200))
        self.treq.json_content.return_value = succeed({'server': {}})

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 1)
        self.failureResultOf(d, UnexpectedServerStatus)

    def test_delete_and_verify_fails_if_delete_500s(self):
        """
        :func:`delete_and_verify` fails if the deletion response code is
        neither a 404 nor a 204
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=500))

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 0)
        self.failureResultOf(d, RequestError)

    def test_delete_and_verify_fails_if_verify_500s(self):
        """
        :func:`delete_and_verify` fails if the verification response code is
        neither a 404 nor a 200
        """
        self.treq.delete.return_value = succeed(mock.Mock(code=204))
        self.treq.get.return_value = succeed(mock.Mock(code=500))

        d = self._delete_and_verify()
        self.assertEqual(len(self.bags), 1)
        self.assertEqual(self.treq.delete.call_count, 1)
        self.assertEqual(self.treq.get.call_count, 1)
        self.failureResultOf(d, RequestError)

    def test_verified_delete_retries_until_success(self):
        """
        If the first delete didn't work, wait a bit and try again until the
        server has been deleted, since a server can sit in DELETE state for a
        bit.  Deferred only callbacks when the deletion is done.

        It also logs deletion success.
        """
        delete_and_verify = patch(
            self, 'otter.worker.launch_server_v1.delete_and_verify')
        delete_and_verify.side_effect = lambda *a, **kw: fail(Exception("bad"))

        d = verified_delete(self.log, 'http://url/', self.request_bag,
                            'serverId', exp_start=2, max_retries=2,
                            clock=self.clock)
        self.assertEqual(delete_and_verify.call_count, 1)
        self.assertNoResult(d)

        delete_and_verify.side_effect = lambda *a, **kw: None

        self.clock.advance(2)
        self.assertEqual(
            delete_and_verify.mock_calls,
            [mock.call(matches(IsBoundWith(server_id='serverId')),
                       'http://url/',
                       self.request_bag, 'serverId', self.clock)] * 2)
        self.successResultOf(d)

        # the loop has stopped
        self.clock.pump([5])
        self.assertEqual(delete_and_verify.call_count, 2)

        # success logged
        self.log.msg.assert_called_with(
            matches(StartsWith("Server deleted successfully")),
            server_id='serverId', time_delete=2.0)

    def test_verified_delete_retries_verification_until_timeout(self):
        """
        If the deleting fails until the timeout, log a failure and do not
        keep trying to delete.
        """
        delete_and_verify = patch(
            self, 'otter.worker.launch_server_v1.delete_and_verify')
        delete_and_verify.side_effect = (
            lambda *a, **kw: fail(DummyException("bad")))

        d = verified_delete(self.log, 'http://url/', self.request_bag,
                            'serverId', exp_start=2, max_retries=2,
                            clock=self.clock)
        self.assertNoResult(d)

        self.clock.advance(2)
        self.assertNoResult(d)
        self.assertEqual(delete_and_verify.call_count, 2)

        self.clock.advance(4)
        self.failureResultOf(d, DummyException)
        self.assertEqual(
            delete_and_verify.mock_calls,
            [mock.call(matches(IsBoundWith(server_id='serverId')),
                       'http://url/', self.request_bag, 'serverId',
                       self.clock)] * 3)

        # the loop has stopped
        self.clock.pump([16, 32])
        self.assertEqual(delete_and_verify.call_count, 3)


class DefinitelyLBConfigTests(SynchronousTestCase):
    """
    Tests for (maybe) synthesizing load balancer configuration.
    """
    def test_lb_id(self):
        """
        When passed a load balancer id, a load balancer config is synthesized.
        """
        self.assertEqual(_definitely_lb_config("abcd"),
                         {"loadBalancerId": "abcd"})

    def test_clb_config(self):
        """
        When passed a CLB load balancer config, it is returned verbatim.
        """
        lb_config = {"loadBalancerId": "some-clb"}
        self.assertEqual(_definitely_lb_config(lb_config), lb_config)

    def test_rcv3_config(self):
        """
        When passed an RCv3 load balancer config, it is returned verbatim.
        """
        lb_config = {"loadBalancerId": "some-rcv3", "type": "RackConnectV3"}
        self.assertEqual(_definitely_lb_config(lb_config), lb_config)
