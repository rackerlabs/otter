"""Tests for :mod:`otter.integration.lib.cloud_load_balancer`"""
import json

from testtools.matchers import Equals

from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer,
    ContainsAllIPs,
    ExcludesAllIPs,
    HasLength)
from otter.integration.lib.test_nova import Response, get_fake_treq
from otter.util.deferredutils import TimedOutError
from otter.util.http import UpstreamError, headers


class _FakeRCS(object):
    endpoints = {'loadbalancers': 'clburl'}
    token = "token"


pending_update_response = [
    Response(422),
    json.dumps({
        "message": ("Load Balancer '12345' has a status of "
                    "'PENDING_UPDATE' and is considered immutable."),
        "code": 422
    })
]


class CLBTests(SynchronousTestCase):
    """
    Tests for the :class:`CloudLoadBalancer` API calls.
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()
        self.rcs = _FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {
            'headers': headers('token'),
            'pool': self.pool
        }

    def get_clb(self, method, url, treq_args_kwargs, response, str_body):
        """
        Stub out treq, and return a cloud load balancer
        """
        clb = CloudLoadBalancer(
            pool=self.pool,
            treq=get_fake_treq(self, method, url, treq_args_kwargs,
                               (response, str_body)))
        clb.clb_id = 12345
        return clb

    def test_list_nodes(self):
        """
        Listing nodes calls the right endpoint and succeeds on 200.
        """
        clb = self.get_clb('get', 'clburl/loadbalancers/12345/nodes',
                           ((), self.expected_kwargs),
                           Response(200), '{"nodes": []}')
        d = clb.list_nodes(self.rcs)
        self.assertEqual({'nodes': []}, self.successResultOf(d))

    def assert_mutate_function_retries_until_success(
            self, mutate_callable, expected_args, success_response,
            expected_result):
        """
        Assert that some CLB function that mutates the CLB will retry on
        pending update until the function succeeds.

        :param mutate_callable: a callable which takes a clb argument and
            a clock argument - this callable should call the CLB's mutate
            function with the required arguments and return the function's
            return value.  For example:
            ``lambda clb, clk: clb.update_node(..., clock=clk)``
        :param expected_args: What are the expected treq arguments?  This
            should be an array of
            [method, url, (expected args, expected kwargs)]
        :param success_response: a tuple of (Response, string response body)
            which should be the successful response back from the API
        :param expected_result: What is the expected successful result of the
            function that is called by ``mutate_callable``
        """
        clock = Clock()
        clb = self.get_clb(*(expected_args + pending_update_response))

        d = mutate_callable(clb, clock)

        self.assertNoResult(d)
        clock.pump([3])
        self.assertNoResult(d)

        clb.treq = get_fake_treq(
            *([self] + expected_args + [success_response]))

        clock.pump([3])
        self.assertEqual(self.successResultOf(d), expected_result)

    def assert_mutate_function_retries_until_timeout(
            self, mutate_callable, expected_args, timeout=60):
        """
        Assert that some CLB function that mutates the CLB will retry on
        pending update until the function times out.

        :param mutate_callable: a callable which takes a clb argument and
            a clock argument - this callable should call the CLB's mutate
            function with the required arguments and return the function's
            return value.  For example:
            ``lambda clb, clk: clb.update_node(..., clock=clk)``
        :param expected_args: What are the expected treq arguments?  This
            should be an array of
            [method, url, (expected args, expected kwargs)]
        :param int timeout: When does your function time out retrying?
        """
        clock = Clock()
        clb = self.get_clb(*(expected_args + pending_update_response))

        d = mutate_callable(clb, clock)
        self.assertNoResult(d)

        for _ in range((timeout - 1) / 3):
            clock.pump([3])
            self.assertNoResult(d)

        clock.pump([3])
        self.failureResultOf(d, TimedOutError)

    def assert_mutate_function_does_not_retry_if_not_pending_update(
            self, mutate_callable, expected_args):
        """
        Assert that some CLB function that mutates the CLB will not retry if
        the error is not a pending update.

        :param mutate_callable: a callable which takes a clb argument and
            a clock argument - this callable should call the CLB's mutate
            function with the required arguments and return the function's
            return value.  For example:
            ``lambda clb, clk: clb.update_node(..., clock=clk)``
        :param expected_args: What are the expected treq arguments?  This
            should be an array of
            [method, url, (expected args, expected kwargs)]
        """
        clock = Clock()
        pending_delete = {
            "message": ("Load Balancer '12345' has a status of "
                        "'PENDING_DELETE' and is considered immutable."),
            "code": 422
        }
        clb = self.get_clb(
            *(expected_args + [Response(422), json.dumps(pending_delete)]))
        d = mutate_callable(clb, clock)
        self.failureResultOf(d, UpstreamError)

    def test_update_node(self):
        """
        Update node calls the right endpoint, succeeds on 202, and retries
        on pending update for 60 seconds. It does not retry if the error is
        not PENDING_UPDATE.
        """
        main_treq_args = ['put', 'clburl/loadbalancers/12345/nodes/54321',
                          (('{"node": {"weight": 5}}',), self.expected_kwargs)]

        def update(clb, clock):
            return clb.update_node(self.rcs, 54321, weight=5, clock=clock)

        self.assert_mutate_function_retries_until_success(
            update, main_treq_args, (Response(202), ""), "")

        self.assert_mutate_function_retries_until_timeout(
            update, main_treq_args, 60)

        self.assert_mutate_function_does_not_retry_if_not_pending_update(
            update, main_treq_args)

    def test_delete_node(self):
        """
        Deleting one or more nodes calls the right endpoint, succeeds on
        202, and retries on pending update for 60 seconds. It does not
        retry if the error is not PENDING_UPDATE.
        """
        self.expected_kwargs['params'] = [("id", 11111), ("id", 22222)]
        main_treq_args = ['delete', 'clburl/loadbalancers/12345/nodes',
                          ((), self.expected_kwargs)]

        def delete(clb, clock):
            return clb.delete_nodes(self.rcs, (11111, 22222), clock=clock)

        self.assert_mutate_function_retries_until_success(
            delete, main_treq_args, (Response(202), ""), "")

        self.assert_mutate_function_retries_until_timeout(
            delete, main_treq_args, 60)

        self.assert_mutate_function_does_not_retry_if_not_pending_update(
            delete, main_treq_args)

    def test_add_node(self):
        """
        Adding one or more nodes calls the right endpoint, succeeds on
        202, and retries on pending update for 60 seconds.  It does not
        retry if the error is not PENDING_UPDATE.
        """
        nodes_to_add = {"nodes": [
            {
                "address": "10.2.2.3",
                "port": 80,
                "condition": "ENABLED",
                "type": "PRIMARY"
            },
            {
                "address": "10.2.2.4",
                "port": 81,
                "condition": "ENABLED",
                "type": "SECONDARY"
            }]}

        main_treq_args = ['post', 'clburl/loadbalancers/12345/nodes',
                          ((json.dumps(nodes_to_add),), self.expected_kwargs)]

        def add(clb, clock):
            return clb.add_nodes(self.rcs, nodes_to_add["nodes"], clock=clock)

        self.assert_mutate_function_retries_until_success(
            add, main_treq_args, (Response(202), json.dumps(nodes_to_add)),
            nodes_to_add)

        self.assert_mutate_function_retries_until_timeout(
            add, main_treq_args, 60)

        self.assert_mutate_function_does_not_retry_if_not_pending_update(
            add, main_treq_args)

    def get_fake_treq_for_delete(self, get_response, del_response=None):
        """
        Return a CLB for use with deleting a CLB - this is different than
        the one returned by `get_clb` because it requires stubbing out two
        treq requests.
        """
        del_response = del_response or Response(202)

        class FakeTreq(object):
            def delete(cls, _url, *args, **kwargs):
                # args and kwargs are the same as the get ones
                self.assertEqual(args, ())
                self.assertEqual(kwargs, self.expected_kwargs)
                self.assertEqual(_url, 'clburl/loadbalancers/{0}'.format(
                    self.clb_id))
                return succeed(del_response)

            def get(cls, _url, *args, **kwargs):
                cls.delete(_url, *args, **kwargs)
                return succeed(get_response)

            def content(cls, resp):
                return succeed(resp.strbody)

            def json_content(cls, resp):
                return succeed(json.loads(resp.strbody))

        return FakeTreq()

    def test_delete_clb_retries_until_success(self):
        """
        Deleting a CLB will retry until the CLB is deleted (or in error or
        suspended mode, in which case it will give up).
        """
        self.clb_id = 12345

        success_treqs = [
            # All of these particular immutable states count as success.
            self.get_fake_treq_for_delete(
                Response(200, strbody=json.dumps(
                    {"loadBalancer": {"status": state}})),
                del_response=Response(400))
            for state in ("PENDING_DELETE", "DELETED", "ERROR", "SUSPENDED")
        ] + [
            # 404 from get-ting the server, meaning it's already gone.
            self.get_fake_treq_for_delete(
                Response(404, strbody=(
                    '{"message": "No such load balancer", "code": 404}')),
                del_response=Response(400))
        ]

        for success_treq in success_treqs:
            clock = Clock()
            _treq = self.get_fake_treq_for_delete(
                Response(
                    200,
                    strbody='{"loadBalancer": {"status": "PENDING_UPDATE"}}'),
                del_response=Response(400))

            clb = CloudLoadBalancer(pool=self.pool, treq=_treq)
            clb.clb_id = self.clb_id

            d = clb.delete(self.rcs, clock=clock)

            self.assertNoResult(d)
            clock.pump([3])
            self.assertNoResult(d)

            clb.treq = success_treq
            clock.pump([3])
            self.assertEqual(self.successResultOf(d), None)

    def test_delete_clb_retries_until_timeout(self):
        """
        Deleting a CLB will retry if the state wonky until it times out.
        """
        clock = Clock()
        self.clb_id = 12345
        _treq = self.get_fake_treq_for_delete(
            Response(
                200,
                strbody='{"loadBalancer": {"status": "PENDING_UPDATE"}}'),
            del_response=Response(400))

        clb = CloudLoadBalancer(pool=self.pool, treq=_treq)
        clb.clb_id = self.clb_id
        d = clb.delete(self.rcs, clock=clock)
        self.assertNoResult(d)

        timeout = 60
        for _ in range((timeout - 1) / 3):
            clock.pump([3])
            self.assertNoResult(d)

        clock.pump([3])
        self.failureResultOf(d, TimedOutError)

    def test_delete_clb_does_not_retry_on_get_failure(self):
        """
        Deleting a CLB will retry if the state wonky until it times out.
        """
        clock = Clock()
        self.clb_id = 12345
        _treq = self.get_fake_treq_for_delete(
            Response(400, strbody="Something is wrong"))

        clb = CloudLoadBalancer(pool=self.pool, treq=_treq)
        clb.clb_id = self.clb_id

        d = clb.delete(self.rcs, clock=clock)
        self.failureResultOf(d, UpstreamError)


class WaitForNodesTestCase(SynchronousTestCase):
    """
    Tests for :func:`CloudLoadBalancer.wait_for_nodes`.
    """
    def setUp(self):
        """
        Set up fake pool, clock, treq, responses, and RCS.
        """
        self.pool = object()
        self.nodes = {'nodes': []}
        self.clock = Clock()
        self.get_calls = 0

        class FakeTreq(object):
            @classmethod
            def get(cls, url, headers, pool):
                self.get_calls += 1
                self.assertIs(self.pool, pool)
                self.assertEqual(["token"], headers.get('x-auth-token'))
                self.assertEqual(['clburl', 'loadbalancers', 'clb_id',
                                  'nodes'],
                                 url.split('/'))
                return succeed(Response(200))

            @classmethod
            def json_content(cls, resp):
                return succeed(self.nodes)

        self.rcs = _FakeRCS()
        self.clb = CloudLoadBalancer(pool=self.pool, treq=FakeTreq)
        self.clb.clb_id = 'clb_id'

    def test_retries_until_matcher_matches(self):
        """
        If the matcher does not matches the load balancer state, retries until
        it does.
        """
        d = self.clb.wait_for_nodes(
            self.rcs,
            Equals(['done']),
            timeout=5,
            period=1,
            clock=self.clock)
        self.clock.pump((1, 1, 1))
        self.assertNoResult(d)
        self.assertEqual(4, self.get_calls)

        self.nodes = {'nodes': ['done']}
        self.clock.pump([1])
        self.assertEqual(['done'], self.successResultOf(d))
        self.assertEqual(5, self.get_calls)

    def test_retries_until_timeout(self):
        """
        If the matcher does not matches the load balancer state, retries until
        it times out.
        """
        d = self.clb.wait_for_nodes(
            self.rcs,
            Equals(['done']),
            timeout=5,
            period=1,
            clock=self.clock)
        self.clock.pump((1, 1, 1, 1, 1))
        self.assertEqual(5, self.get_calls)
        self.failureResultOf(d, TimedOutError)


class MatcherTestCase(SynchronousTestCase):
    """
    Tests for the CLB matchers.
    """
    def test_contains_all_ips_success(self):
        """
        :class:`ContainsAllIPs` succeeds when the nodes contain all the IPs
        given.
        """
        matcher = ContainsAllIPs(['10.0.0.1', '10.0.0.2', '10.0.0.2'])
        mismatch = matcher.match([
            {'id': i, 'address': '10.0.0.{0}'.format(i)}
            for i in (1, 2)
        ])
        self.assertEqual(None, mismatch)

    def test_contains_all_ips_failure(self):
        """
        :class:`ContainsAllIPs` fail when the nodes contain only some or
        none of the all the IPs given.
        """
        matcher = ContainsAllIPs(['10.0.0.1', '10.0.0.2', '10.0.0.2'])
        self.assertNotEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 3)]),
            "Partial match succeeds when all should be required."
        )
        self.assertNotEqual(None, matcher.match([]), "No matches succed.")

    def test_excludes_all_ips_success(self):
        """
        :class:`ExcludesAllIPs` succeeds when the nodes do not contain any of
        the IPs given.
        """
        matcher = ExcludesAllIPs(['10.0.0.1', '10.0.0.1'])
        mismatch = matcher.match([
            {'id': i, 'address': '10.0.0.{0}'.format(i)}
            for i in (2, 3)
        ])
        self.assertEqual(None, mismatch)

    def test_excludes_all_ips_failure(self):
        """
        :class:`ExcludesAllIPs` fails when the nodes contain any or all of
        the IPs given.
        """
        matcher = ExcludesAllIPs(['10.0.0.1', '10.0.0.2'])
        self.assertNotEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 2)]),
            "Complete match succeeds when none should be present."
        )
        self.assertNotEqual(
            None,
            matcher.match([{'id': 1, 'address': '10.0.0.1'}]),
            "Partial match succeeds when none should be present."
        )

    def test_has_length(self):
        """
        :class:`HasLength` only succeeds when the number of nodes matches the
        length given.
        """
        matcher = HasLength(2)
        self.assertNotEqual(
            None,
            matcher.match([{'id': 1, 'address': '10.0.0.1'}])
        )
        self.assertNotEqual(None, matcher.match([]))
        self.assertEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 2)]))
