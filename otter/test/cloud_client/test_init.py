"""Tests for otter.cloud_client"""

import json
from functools import partial
from uuid import uuid4

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    TypeDispatcher,
    base_dispatcher,
    sync_perform)
from effect.testing import EQFDispatcher, SequenceDispatcher, perform_sequence

import mock

import six

from toolz.dicttoolz import assoc

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from txeffect import perform

from otter.auth import Authenticate, InvalidateToken
from otter.cloud_client import (
    CLBDeletedError,
    CLBDuplicateNodesError,
    CLBImmutableError,
    CLBNodeLimitError,
    CLBNotActiveError,
    CLBRateLimitError,
    CreateServerConfigurationError,
    CreateServerOverQuoteError,
    NoSuchCLBError,
    NoSuchCLBNodeError,
    NoSuchServerError,
    NovaComputeFaultError,
    NovaRateLimitError,
    ServerMetadataOverLimitError,
    ServiceRequest,
    TenantScope,
    _Throttle,
    _default_throttler,
    _perform_throttle,
    add_bind_service,
    add_clb_nodes,
    change_clb_node,
    check_stack,
    concretize_service_request,
    create_server,
    create_stack,
    delete_stack,
    get_clb_node_feed,
    get_clb_nodes,
    get_clbs,
    get_cloud_client_dispatcher,
    get_server_details,
    list_servers_details_all,
    list_servers_details_page,
    list_stacks_all,
    perform_tenant_scope,
    remove_clb_nodes,
    service_request,
    set_nova_metadata_item,
    update_stack)
from otter.constants import ServiceType
from otter.indexer import atom
from otter.log.intents import Log
from otter.test.utils import (
    StubResponse,
    const,
    nested_sequence,
    raise_,
    resolve_effect,
    stub_json_response,
    stub_pure_response
)
from otter.test.worker.test_launch_server_v1 import fake_service_catalog
from otter.util.config import set_config_data
from otter.util.http import APIError, headers
from otter.util.pure_http import Request, has_code
from otter.util.weaklocks import WeakLocks


def make_service_configs():
    """
    Generate service configs for performing service requests.
    """
    return {
        ServiceType.CLOUD_SERVERS: {
            'name': 'cloudServersOpenStack',
            'region': 'DFW'},
        ServiceType.CLOUD_LOAD_BALANCERS: {
            'name': 'cloudLoadBalancers',
            'region': 'DFW'},
        ServiceType.CLOUD_FEEDS: {
            'name': 'cloud_feeds',
            'region': 'DFW',
            'url': 'special cloudfeeds url'
        },
        ServiceType.CLOUD_ORCHESTRATION: {
            'name': 'cloudOrchestration',
            'region': 'DFW'
        }
    }


def resolve_authenticate(eff, token='token'):
    """Resolve an Authenticate effect with test data."""
    return resolve_effect(eff, (token, fake_service_catalog))


def service_request_eqf(stub_response):
    """
    Return a function to be used as the value matching a ServiceRequest in
    :class:`EQFDispatcher`.
    """
    def resolve_service_request(service_request_intent):
        eff = concretize_service_request(
            authenticator=object(),
            log=object(),
            service_configs=make_service_configs(),
            throttler=lambda stype, method, tid: None,
            tenant_id='000000',
            service_request=service_request_intent)

        # "authenticate"
        eff = resolve_authenticate(eff)
        # make request
        return resolve_effect(eff, stub_response)

    return resolve_service_request


def log_intent(msg_type, body, log_as_json=True, req_body=''):
    """
    Return a :obj:`Log` intent for the given mesasge type and body.
    """
    body = json.dumps(body, sort_keys=True) if log_as_json else body
    return Log(
        msg_type,
        {'url': "original/request/URL",
         'method': 'method',
         'request_id': "original-request-id",
         'response_body': body, 'request_body': req_body}
    )


class BindServiceTests(SynchronousTestCase):
    """Tests for :func:`add_bind_service`."""

    def setUp(self):
        """Save some common parameters."""
        self.log = object()

    def request_func(self, method, url, headers=None, data=None):
        """
        A request func for testing that just returns its args.
        """
        return method, url, headers, data

    def test_add_bind_service(self):
        """
        URL paths passed to the request function are appended to the
        endpoint of the service in the specified region for the tenant.
        """
        request = add_bind_service(fake_service_catalog,
                                   'cloudServersOpenStack', 'DFW', self.log,
                                   self.request_func)
        self.assertEqual(
            request('get', 'foo'),
            ('get', 'http://dfw.openstack/foo', None, None))


class ServiceRequestTests(SynchronousTestCase):
    """Tests for :func:`service_request`."""
    def test_defaults(self):
        """Default arguments are populated."""
        eff = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'foo')
        self.assertEqual(
            eff,
            Effect(
                ServiceRequest(
                    service_type=ServiceType.CLOUD_SERVERS,
                    method='GET',
                    url='foo',
                    headers=None,
                    data=None,
                    params=None,
                    log=None,
                    reauth_codes=(401, 403),
                    success_pred=has_code(200),
                    json_response=True
                )
            )
        )


class PerformServiceRequestTests(SynchronousTestCase):
    """Tests for :func:`concretize_service_request`."""
    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.service_configs = make_service_configs()
        eff = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        self.svcreq = eff.intent

    def _concrete(self, svcreq, throttler=None, **kwargs):
        """
        Call :func:`concretize_service_request` with premade test objects.
        """
        if throttler is None:
            def throttler(stype, method, tid):
                pass
        return concretize_service_request(
            self.authenticator, self.log, self.service_configs,
            throttler,
            1, svcreq,
            **kwargs)

    def test_authenticates(self):
        """Auth is done before making the request."""
        eff = self._concrete(self.svcreq)
        expected_intent = Authenticate(self.authenticator, 1, self.log)
        self.assertEqual(eff.intent, expected_intent)
        next_eff = resolve_authenticate(eff)
        # The next effect in the chain is the requested HTTP request,
        # with appropriate auth headers
        self.assertEqual(
            next_eff.intent,
            Request(method='GET', url='http://dfw.openstack/servers',
                    headers=headers('token'), log=self.log))

    def test_invalidate_on_auth_error_code(self):
        """
        Upon authentication error, the auth cache is invalidated.
        """
        eff = self._concrete(self.svcreq)
        next_eff = resolve_authenticate(eff)
        # When the HTTP response is an auth error, the auth cache is
        # invalidated, by way of the next effect:
        invalidate_eff = resolve_effect(next_eff, stub_pure_response("", 401))
        expected_intent = InvalidateToken(self.authenticator, 1)
        self.assertEqual(invalidate_eff.intent, expected_intent)
        self.assertRaises(APIError, resolve_effect, invalidate_eff, None)

    def test_binds_url(self):
        """
        Binds a URL from service config if it has URL instead of binding
        URL from service catalog
        """
        self.service_configs[ServiceType.CLOUD_SERVERS]['url'] = 'myurl'
        eff = self._concrete(self.svcreq)
        next_eff = resolve_authenticate(eff)
        # URL in HTTP request is configured URL
        self.assertEqual(
            next_eff.intent,
            Request(method='GET', url='myurl/servers',
                    headers=headers('token'), log=self.log))

    def test_json(self):
        """
        JSON-serializable requests are dumped before being sent, and
        JSON-serialized responses are parsed.
        """
        input_json = {"a": 1}
        output_json = {"b": 2}
        svcreq = service_request(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                 data=input_json).intent
        eff = self._concrete(svcreq)

        # Input is serialized
        next_eff = resolve_authenticate(eff)
        self.assertEqual(next_eff.intent.data, json.dumps(input_json))

        # Output is parsed
        response, body = stub_pure_response(json.dumps(output_json))
        result = resolve_effect(next_eff, (response, body))
        self.assertEqual(result, (response, output_json))

    def test_no_json_response(self):
        """
        ``json_response`` can be set to :data:`False` to get the response
        object and the plaintext body of the response.
        """
        svcreq = service_request(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                 json_response=False).intent
        eff = self._concrete(svcreq)
        next_eff = resolve_authenticate(eff)
        stub_response = stub_pure_response("foo")
        result = resolve_effect(next_eff, stub_response)
        self.assertEqual(result, stub_response)

    def test_no_json_parsing_on_error(self):
        """
        Whatever ``json_response`` is set to, it is ignored, if the response
        does not pass the success predicate (because errors may just be
        HTML or otherwise not JSON parsable, even if the success response
        would have been).
        """
        svcreq = service_request(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                 json_response=True).intent
        eff = self._concrete(svcreq)
        next_eff = resolve_authenticate(eff)
        stub_response = stub_pure_response("THIS IS A FAILURE", 500)
        with self.assertRaises(APIError) as cm:
            resolve_effect(next_eff, stub_response)

        self.assertEqual(cm.exception.body, "THIS IS A FAILURE")

    def test_params(self):
        """Params are passed through."""
        svcreq = service_request(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                 params={"foo": ["bar"]}).intent
        eff = self._concrete(svcreq)
        pure_request_eff = resolve_authenticate(eff)
        self.assertEqual(pure_request_eff.intent.params, {"foo": ["bar"]})

    def test_throttling(self):
        """
        When the throttler function returns a bracketing function, it's used to
        throttle the request.
        """
        def throttler(stype, method, tid):
            if (stype == ServiceType.CLOUD_SERVERS and
                    method == 'get' and tid == 1):
                return bracket
        bracket = object()
        svcreq = service_request(
            ServiceType.CLOUD_SERVERS, 'GET', 'servers').intent

        response = stub_pure_response({}, 200)
        seq = SequenceDispatcher([
            (_Throttle(bracket=bracket, effect=mock.ANY),
             nested_sequence([
                 (Authenticate(authenticator=self.authenticator,
                               tenant_id=1,
                               log=self.log),
                  lambda i: ('token', fake_service_catalog)),
                 (Request(method='GET', url='http://dfw.openstack/servers',
                          headers=headers('token'), log=self.log),
                  lambda i: response),
             ])),
        ])

        eff = self._concrete(svcreq, throttler=throttler)
        with seq.consume():
            result = sync_perform(seq, eff)
        self.assertEqual(result, (response[0], {}))


class ThrottleTests(SynchronousTestCase):
    """Tests for :obj:`_Throttle` and :func:`_perform_throttle`."""

    def test_perform_throttle(self):
        """
        The bracket given to :obj:`_Throttle` is used to call the nested
        performer.
        """
        def bracket(f, *args, **kwargs):
            return f(*args, **kwargs).addCallback(lambda r: ('bracketed', r))
        throttle = _Throttle(bracket=bracket, effect=Effect(Constant('foo')))
        dispatcher = ComposedDispatcher([
            TypeDispatcher({_Throttle: _perform_throttle}),
            base_dispatcher])
        result = sync_perform(dispatcher, Effect(throttle))
        self.assertEqual(result, ('bracketed', 'foo'))


class DefaultThrottlerTests(SynchronousTestCase):
    """Tests for :func:`_default_throttler`."""

    def tearDown(self):
        set_config_data(None)

    def test_mismatch(self):
        """policy doesn't have a throttler for random junk."""
        bracket = _default_throttler(
            WeakLocks(), None, 'foo', 'get', 'any-tenant')
        self.assertIs(bracket, None)

    def test_no_config(self):
        """ No config results in no throttling """
        bracket = _default_throttler(
            WeakLocks(), None, ServiceType.CLOUD_SERVERS, 'get', 'any-tenant')
        self.assertIs(bracket, None)

    def test_post_and_delete_not_the_same(self):
        """
        The throttlers for POST and DELETE to cloud servers are different.
        """
        set_config_data(
            {"cloud_client": {"throttling": {"create_server_delay": 1,
                                             "delete_server_delay": 0.4}}})
        clock = Clock()
        locks = WeakLocks()
        deleter = _default_throttler(
            locks, clock, ServiceType.CLOUD_SERVERS, 'delete', 'any-tenant')
        poster = _default_throttler(
            locks, clock, ServiceType.CLOUD_SERVERS, 'post', 'any-tenant')
        self.assertIsNot(deleter, poster)

    def _test_throttle(self, cfg_name, stype, method):
        """Test a specific throttling configuration."""
        locks = WeakLocks()
        set_config_data(
            {'cloud_client': {'throttling': {cfg_name: 500}}})
        self.addCleanup(set_config_data, {})
        clock = Clock()
        bracket = _default_throttler(locks, clock, stype, method, 'tenant1')
        if bracket is None:
            self.fail("No throttler for %s and %s" % (stype, method))
        d = bracket(lambda: 'foo')
        clock.advance(499)
        self.assertNoResult(d)
        clock.advance(500)
        self.assertEqual(self.successResultOf(d), 'foo')

        # also make sure that the lock is shared between different calls to the
        # throttler.
        bracket1 = _default_throttler(locks, clock, stype, method, 'tenant1')
        result1 = bracket1(lambda: 'bar1')
        bracket2 = _default_throttler(locks, clock, stype, method, 'tenant1')
        result2 = bracket2(lambda: 'bar2')
        clock.advance(499)
        self.assertNoResult(result1)
        self.assertNoResult(result2)
        clock.advance(1)
        self.assertEqual(self.successResultOf(result1), 'bar1')
        self.assertNoResult(result2)
        clock.advance(500)
        self.assertEqual(self.successResultOf(result2), 'bar2')

    def _test_tenant(self, cfg_name, stype, method):
        """
        Test a specific throttling configuration, and ensure that locks are
        per-tenant.
        """
        locks = WeakLocks()
        set_config_data(
            {'cloud_client': {'throttling': {cfg_name: 500}}})
        self.addCleanup(set_config_data, {})
        clock = Clock()
        bracket1 = _default_throttler(locks, clock, stype, method, 'tenant1')
        if bracket1 is None:
            self.fail("No throttler for %s and %s" % (stype, method))
        result1 = bracket1(lambda: 'bar1')
        bracket2 = _default_throttler(locks, clock, stype, method, 'tenant2')
        result2 = bracket2(lambda: 'bar2')
        self.assertNoResult(result1)
        self.assertNoResult(result2)
        clock.advance(500)
        self.assertEqual(self.successResultOf(result1), 'bar1')
        self.assertEqual(self.successResultOf(result2), 'bar2')

    def test_delay_configurable(self):
        """Delays are configurable."""
        self._test_throttle(
            'create_server_delay', ServiceType.CLOUD_SERVERS, 'post')
        self._test_throttle(
            'delete_server_delay', ServiceType.CLOUD_SERVERS, 'delete')
        self._test_throttle(
            'create_server_delay', ServiceType.CLOUD_SERVERS, 'post')
        self._test_throttle(
            'delete_server_delay', ServiceType.CLOUD_SERVERS, 'delete')
        self._test_throttle(
            'get_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'get')
        self._test_throttle(
            'post_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'post')
        self._test_throttle(
            'put_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'put')
        self._test_throttle(
            'delete_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'delete')

    def test_tenant_specific_locking(self):
        self._test_tenant(
            'get_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'get')
        self._test_tenant(
            'post_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'post')
        self._test_tenant(
            'put_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'put')
        self._test_tenant(
            'delete_clb_delay', ServiceType.CLOUD_LOAD_BALANCERS, 'delete')


class GetCloudClientDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_cloud_client_dispatcher`."""

    def test_performs_throttle(self):
        """:func:`_perform_throttle` performs :obj:`_Throttle`."""
        dispatcher = get_cloud_client_dispatcher(None, None, None, None)
        throttle = _Throttle(bracket=lambda f, *a, **kw: f(*a, **kw),
                             effect=Effect(Constant('foo')))
        self.assertIs(dispatcher(throttle), _perform_throttle)

    @mock.patch('twisted.internet.defer.DeferredLock.run')
    def test_performs_tenant_scope(self, deferred_lock_run):
        """
        :func:`perform_tenant_scope` performs :obj:`TenantScope`, and uses the
        default throttler
        """
        # We want to ensure
        # 1. the TenantScope can be performed
        # 2. the ServiceRequest is run within a lock, since it matches the
        #    default throttling policy

        set_config_data(
            {"cloud_client": {"throttling": {"create_server_delay": 1,
                                             "delete_server_delay": 0.4}}})
        self.addCleanup(set_config_data, {})
        clock = Clock()
        authenticator = object()
        log = object()
        dispatcher = get_cloud_client_dispatcher(clock, authenticator, log,
                                                 make_service_configs())
        svcreq = service_request(ServiceType.CLOUD_SERVERS, 'POST', 'servers')
        tscope = TenantScope(tenant_id='111', effect=svcreq)

        def run(f, *args, **kwargs):
            result = f(*args, **kwargs)
            result.addCallback(
                lambda x: (x[0], assoc(x[1], 'locked', True)))
            return result
        deferred_lock_run.side_effect = run

        response = stub_pure_response({}, 200)
        seq = SequenceDispatcher([
            (Authenticate(authenticator=authenticator,
                          tenant_id='111', log=log),
             lambda i: ('token', fake_service_catalog)),
            (Request(method='POST', url='http://dfw.openstack/servers',
                     headers=headers('token'), log=log),
             lambda i: response),
        ])

        disp = ComposedDispatcher([seq, dispatcher])
        with seq.consume():
            result = perform(disp, Effect(tscope))
            self.assertNoResult(result)
            clock.advance(1)
            self.assertEqual(self.successResultOf(result),
                             (response[0], {'locked': True}))


class PerformTenantScopeTests(SynchronousTestCase):
    """Tests for :func:`perform_tenant_scope`."""

    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.service_configs = make_service_configs()

        self.throttler = lambda stype, method: None

        def concretize(au, lo, smap, throttler, tenid, srvreq):
            return Effect(Constant(('concretized', au, lo, smap, throttler,
                                    tenid, srvreq)))

        self.dispatcher = ComposedDispatcher([
            TypeDispatcher({
                TenantScope: partial(perform_tenant_scope, self.authenticator,
                                     self.log, self.service_configs,
                                     self.throttler,
                                     _concretize=concretize)}),
            base_dispatcher])

    def test_perform_boring(self):
        """Other effects within a TenantScope are performed as usual."""
        tscope = TenantScope(Effect(Constant('foo')), 1)
        self.assertEqual(sync_perform(self.dispatcher, Effect(tscope)), 'foo')

    def test_perform_service_request(self):
        """
        Performing a :obj:`TenantScope` when it contains a
        :obj:`ServiceRequest` concretizes the :obj:`ServiceRequest` into a
        :obj:`Request` as per :func:`concretize_service_request`.
        """
        ereq = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        tscope = TenantScope(ereq, 1)
        self.assertEqual(
            sync_perform(self.dispatcher, Effect(tscope)),
            ('concretized', self.authenticator, self.log, self.service_configs,
             self.throttler, 1, ereq.intent))

    def test_perform_srvreq_nested(self):
        """
        Concretizing of :obj:`ServiceRequest` effects happens even when they
        are not directly passed as the TenantScope's toplevel Effect, but also
        when they are returned from callbacks down the line.
        """
        ereq = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        eff = Effect(Constant("foo")).on(lambda r: ereq)
        tscope = TenantScope(eff, 1)
        self.assertEqual(
            sync_perform(self.dispatcher, Effect(tscope)),
            ('concretized', self.authenticator, self.log, self.service_configs,
             self.throttler, 1, ereq.intent))


def assert_parses_common_clb_errors(testcase, intent, eff, lb_id):
    """
    Assert that the effect produced performs the common CLB error parsing:
    :class:`CLBImmutableError`, :class:`CLBDescription`,
    :class:`NoSuchCLBError`, :class:`CLBRateLimitError`,
    :class:`APIError`

    :param :obj:`twisted.trial.unittest.TestCase` testcase: Test object
    :param intent: expected ``ServiceRequest`` intent
    :param eff: Effect returned from function being tested
    :param lb_id: ID of load balancer being accessed in the function being
        tested
    """
    json_responses_and_errs = [
        ("Load Balancer '{0}' has a status of 'BUILD' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'PENDING_UPDATE' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'unexpected status' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'PENDING_DELETE' and is "
         "considered immutable.", 422, CLBDeletedError),
        ("The load balancer is deleted and considered immutable.",
         422, CLBDeletedError),
        ("Load balancer not found.", 404, NoSuchCLBError),
        ("LoadBalancer is not ACTIVE", 422, CLBNotActiveError),
        ("The loadbalancer is marked as deleted.", 410, CLBDeletedError),
    ]

    for msg, code, err in json_responses_and_errs:
        msg = msg.format(lb_id)
        resp = stub_pure_response(
            json.dumps({'message': msg, 'code': code, 'details': ''}),
            code)
        with testcase.assertRaises(err) as cm:
            perform_sequence([(intent, service_request_eqf(resp))], eff)
        testcase.assertEqual(cm.exception,
                             err(msg, lb_id=six.text_type(lb_id)))

    # OverLimit Retry is different because it's produced by repose
    over_limit = stub_pure_response(
        json.dumps({
            "overLimit": {
                "message": "OverLimit Retry...",
                "code": 413,
                "retryAfter": "2015-06-13T22:30:10Z",
                "details": "Error Details..."
            }
        }),
        413)
    with testcase.assertRaises(CLBRateLimitError) as cm:
        perform_sequence([(intent, service_request_eqf(over_limit))], eff)
    testcase.assertEqual(
        cm.exception,
        CLBRateLimitError("OverLimit Retry...",
                          lb_id=six.text_type(lb_id)))

    # Ignored errors
    bad_resps = [
        stub_pure_response(
            json.dumps({
                'message': ("Load Balancer '{0}' has a status of 'BROKEN' "
                            "and is considered immutable."),
                'code': 422}),
            422),
        stub_pure_response(
            json.dumps({
                'message': ("The load balancer is deleted and considered "
                            "immutable"),
                'code': 404}),
            404),
        stub_pure_response(
            json.dumps({
                'message': "Cloud load balancers is down",
                'code': 500}),
            500),
        stub_pure_response(
            json.dumps({
                'message': "this is not an over limit message",
                'code': 413}),
            413),
        stub_pure_response("random repose error message", 404),
        stub_pure_response("random repose error message", 413)
    ]

    for resp in bad_resps:
        with testcase.assertRaises(APIError) as cm:
            perform_sequence([(intent, service_request_eqf(resp))], eff)
        testcase.assertEqual(
            cm.exception,
            APIError(headers={}, code=resp[0].code, body=resp[1],
                     method='method', url='original/request/URL'))


class CLBClientTests(SynchronousTestCase):
    """
    Tests for CLB client functions, such as :obj:`change_clb_node`.
    """
    @property
    def lb_id(self):
        """What is my LB ID"""
        return "123456"

    def test_change_clb_node(self):
        """
        Produce a request for modifying a node on a load balancer, which
        returns a successful result on 202.

        Parse the common CLB errors, and :class:`NoSuchCLBNodeError`.
        """
        eff = change_clb_node(lb_id=self.lb_id, node_id='1234',
                              condition="DRAINING", weight=50,
                              _type='SECONDARY')
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            'loadbalancers/{0}/nodes/1234'.format(self.lb_id),
            data={'node': {'condition': 'DRAINING',
                           'weight': 50, 'type': 'SECONDARY'}},
            success_pred=has_code(202))

        # success
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('', 202)))])
        self.assertEqual(sync_perform(dispatcher, eff),
                         stub_pure_response(None, 202))

        # NoSuchCLBNode failure
        msg = "Node with id #1234 not found for loadbalancer #{0}".format(
            self.lb_id)
        no_such_node = stub_pure_response(
            json.dumps({'message': msg, 'code': 404}), 404)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(no_such_node))])

        with self.assertRaises(NoSuchCLBNodeError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            NoSuchCLBNodeError(msg, lb_id=six.text_type(self.lb_id),
                               node_id=u'1234'))

        # all the common failures
        assert_parses_common_clb_errors(self, expected.intent, eff, "123456")

    def test_change_clb_node_default_type(self):
        """
        Produce a request for modifying a node on a load balancer with the
        default type, which returns a successful result on 202.
        """
        eff = change_clb_node(lb_id=self.lb_id, node_id='1234',
                              condition="DRAINING", weight=50)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            'loadbalancers/{0}/nodes/1234'.format(self.lb_id),
            data={'node': {'condition': 'DRAINING',
                           'weight': 50, 'type': 'PRIMARY'}},
            success_pred=has_code(202))

        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('', 202)))])
        self.assertEqual(sync_perform(dispatcher, eff),
                         stub_pure_response(None, 202))

    def test_add_clb_nodes(self):
        """
        Produce a request for adding nodes to a load balancer, which returns
        a successful result on a 202.

        Parse the common CLB errors, and a :class:`CLBDuplicateNodesError`.
        """
        nodes = [{"address": "1.1.1.1", "port": 80, "condition": "ENABLED"},
                 {"address": "1.1.1.2", "port": 80, "condition": "ENABLED"},
                 {"address": "1.1.1.5", "port": 81, "condition": "ENABLED"}]

        eff = add_clb_nodes(lb_id=self.lb_id, nodes=nodes)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            'loadbalancers/{0}/nodes'.format(self.lb_id),
            data={'nodes': nodes},
            success_pred=has_code(202))

        # success
        seq = [
            (expected.intent, lambda i: stub_json_response({}, 202, {})),
            (log_intent('request-add-clb-nodes', {}), lambda _: None)]
        self.assertEqual(perform_sequence(seq, eff),
                         (StubResponse(202, {}), {}))

        # CLBDuplicateNodesError failure
        msg = ("Duplicate nodes detected. One or more nodes already "
               "configured on load balancer.")
        duplicate_nodes = stub_pure_response(
            json.dumps({'message': msg, 'code': 422}), 422)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(duplicate_nodes))])

        with self.assertRaises(CLBDuplicateNodesError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            CLBDuplicateNodesError(msg, lb_id=six.text_type(self.lb_id)))

        # CLBNodeLimitError failure
        msg = "Nodes must not exceed 25 per load balancer."
        limit = stub_pure_response(
            json.dumps({'message': msg, 'code': 413}), 413)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(limit))])

        with self.assertRaises(CLBNodeLimitError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            CLBNodeLimitError(msg, lb_id=six.text_type(self.lb_id),
                              node_limit=25))

        # all the common failures
        assert_parses_common_clb_errors(self, expected.intent, eff, "123456")

    def expected_node_removal_req(self, nodes=(1, 2)):
        """
        :return: Expected effect for a node removal request.
        """
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            'loadbalancers/{}/nodes'.format(self.lb_id),
            params={'id': map(str, nodes)},
            success_pred=has_code(202))

    def test_remove_clb_nodes_success(self):
        """
        A DELETE request is sent, and the Effect returns None if 202 is
        returned.
        """
        eff = remove_clb_nodes(self.lb_id, [1, 2])
        seq = [
            (self.expected_node_removal_req().intent,
             service_request_eqf(stub_pure_response({}, 202))),
        ]
        result = perform_sequence(seq, eff)
        self.assertIs(result, None)

    def test_remove_clb_nodes_handles_standard_clb_errors(self):
        """
        Common CLB errors about it being in a deleted state, pending update,
        etc. are handled.
        """
        eff = remove_clb_nodes(self.lb_id, [1, 2])
        assert_parses_common_clb_errors(
            self, self.expected_node_removal_req().intent, eff, "123456")

    def test_remove_clb_nodes_non_202(self):
        """Any random HTTP response code is bubbled up as an APIError."""
        eff = remove_clb_nodes(self.lb_id, [1, 2])
        seq = [
            (self.expected_node_removal_req().intent,
             service_request_eqf(stub_pure_response({}, 200))),
        ]
        self.assertRaises(APIError, perform_sequence, seq, eff)

    def test_remove_clb_nodes_random_400(self):
        """Random 400s that can't be parsed are bubbled up as an APIError."""
        error_bodies = [
            {'validationErrors': {'messages': ['bar']}},
            {'messages': 'bar'},
            {'validationErrors': {'messages': []}},
            "random non-json"
        ]
        for body in error_bodies:
            eff = remove_clb_nodes(self.lb_id, [1, 2])
            seq = [
                (self.expected_node_removal_req().intent,
                 service_request_eqf(stub_pure_response(body, 400))),
            ]
            self.assertRaises(APIError, perform_sequence, seq, eff)

    def test_remove_clb_nodes_retry_on_some_invalid_nodes(self):
        """
        When CLB returns an error indicating that some of the nodes are
        invalid, the request is retried without the offending nodes.
        """
        eff = remove_clb_nodes(self.lb_id, [1, 2, 3, 4])
        response = stub_pure_response(
            {'validationErrors': {'messages': [
                'Node ids 1,3 are not a part of your loadbalancer']}},
            400)
        response2 = stub_pure_response({}, 202)
        seq = [
            (self.expected_node_removal_req([1, 2, 3, 4]).intent,
             service_request_eqf(response)),
            (self.expected_node_removal_req([2, 4]).intent,
             service_request_eqf(response2))
        ]
        self.assertIs(perform_sequence(seq, eff), None)

    def test_get_clbs(self):
        """Returns all the load balancer details from the LBs endpoint."""
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS, 'GET', 'loadbalancers')
        req = get_clbs()
        body = {'loadBalancers': 'lbs!'}
        seq = [
            (expected.intent, lambda i: stub_json_response(body)),
            (log_intent('request-list-clbs', body), lambda _: None)]
        self.assertEqual(perform_sequence(seq, req), 'lbs!')

    def test_get_clb_nodes(self):
        """:func:`get_clb_nodes` returns all the nodes for a LB."""
        req = get_clb_nodes(self.lb_id)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'GET', 'loadbalancers/123456/nodes')
        body = {'nodes': 'nodes!'}
        seq = [
            (expected.intent, lambda i: stub_json_response(body)),
            (log_intent('request-list-clb-nodes', body), lambda _: None)]
        self.assertEqual(perform_sequence(seq, req), 'nodes!')

    def test_get_clb_nodes_error_handling(self):
        """:func:`get_clb_nodes` parses the common CLB errors."""
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'GET', 'loadbalancers/123456/nodes')
        assert_parses_common_clb_errors(
            self, expected.intent, get_clb_nodes(self.lb_id), "123456")


class GetCLBNodeFeedTests(SynchronousTestCase):

    entry = '<entry><summary>{}</summary></entry>'
    feed_fmt = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        '<link rel="next" href="{next_link}"/>{entries}</feed>')

    def svc_intent(self, params={}):
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS, "GET",
            "loadbalancers/12/nodes/13.atom", params=params,
            json_response=False).intent

    def feed(self, next_link, summaries):
        return self.feed_fmt.format(
            next_link=next_link,
            entries=''.join(self.entry.format(s) for s in summaries))

    def test_empty(self):
        """
        Does not goto next link when there are no entries and returns []
        """
        feedstr = self.feed("next-doesnt-matter", [])
        seq = [
            (self.svc_intent(), const(stub_json_response(feedstr))),
            (log_intent("request-get-clb-node-feed", feedstr), const(feedstr))
        ]
        self.assertEqual(
            perform_sequence(seq, get_clb_node_feed("12", "13")), [])

    def test_single_page(self):
        """
        Collects entries and goes to next link if there are entries and returns
        if next one is empty
        """
        feed1_str = self.feed("https://url?page=2", ["summary1", "summ2"])
        feed2_str = self.feed("next-link", [])
        seq = [
            (self.svc_intent(), const(stub_json_response(feed1_str))),
            (log_intent("request-get-clb-node-feed", feed1_str),
             const(feed1_str)),
            (self.svc_intent({"page": ['2']}),
             const(stub_json_response(feed2_str))),
            (log_intent("request-get-clb-node-feed", feed2_str),
             const(feed2_str)),
        ]
        entries = perform_sequence(seq, get_clb_node_feed("12", "13"))
        self.assertEqual(
            [atom.summary(entry) for entry in entries], ["summary1", "summ2"])

    def test_multiple_pages(self):
        """
        Collects entries and goes to next link if there are entries and
        continues until next link returns empty list
        """
        feed1_str = self.feed("https://url?page=2", ["summ1", "summ2"])
        feed2_str = self.feed("https://url?page=3", ["summ3", "summ4"])
        feed3_str = self.feed("next-link", [])
        seq = [
            (self.svc_intent(), const(stub_json_response(feed1_str))),
            (log_intent("request-get-clb-node-feed", feed1_str),
             const(feed1_str)),
            (self.svc_intent({"page": ['2']}),
             const(stub_json_response(feed2_str))),
            (log_intent("request-get-clb-node-feed", feed2_str),
             const(feed2_str)),
            (self.svc_intent({"page": ['3']}),
             const(stub_json_response(feed3_str))),
            (log_intent("request-get-clb-node-feed", feed3_str),
             const(feed3_str)),
        ]
        entries = perform_sequence(seq, get_clb_node_feed("12", "13"))
        self.assertEqual(
            [atom.summary(entry) for entry in entries],
            ["summ1", "summ2", "summ3", "summ4"])

    def test_no_next_link(self):
        """
        Returns entries collected till now if there is no next link
        """
        feedstr = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><summary>summary</summary></entry></feed>')
        seq = [
            (self.svc_intent(), const(stub_json_response(feedstr))),
            (log_intent("request-get-clb-node-feed", feedstr),
             const(feedstr))
        ]
        entries = perform_sequence(seq, get_clb_node_feed("12", "13"))
        self.assertEqual(atom.summary(entries[0]), "summary")

    def test_error_handling(self):
        """
        Parses regular CLB errors and raises corresponding exceptions
        """
        assert_parses_common_clb_errors(
            self, self.svc_intent(), get_clb_node_feed("12", "13"), "12")


def _perform_one_request(intent, effect, response_code, response_body,
                         log_intent=None):
    """
    Perform a request effect using EQFDispatcher, providing the given
    body and status code.
    """
    seq = [(
        intent,
        service_request_eqf(
            stub_pure_response(response_body, response_code))
    )]
    if log_intent is not None:
        seq.append((log_intent, lambda _: None))
    return perform_sequence(seq, effect)


class NovaClientTests(SynchronousTestCase):
    """
    Tests for Nova client functions, such as :obj:`set_nova_metadata_item`.
    """
    def _setup_for_set_nova_metadata_item(self):
        """
        Produce the data needed to test :obj:`set_nova_metadata_item`: a tuple
        of (server_id, expected_effect, real_effect)
        """
        server_id = unicode(uuid4())
        real = set_nova_metadata_item(server_id=server_id, key='k', value='v')
        expected = service_request(
            ServiceType.CLOUD_SERVERS,
            'PUT',
            'servers/{0}/metadata/k'.format(server_id),
            data={'meta': {'k': 'v'}},
            reauth_codes=(401,),
            success_pred=has_code(200))
        return (server_id, expected, real)

    def assert_handles_no_such_server(self, intent, effect, server_id):
        """
        If the provided intent returns a response consistent with a server not
        existing, then performing the effect will raise a
        :class:`NoSuchServerError`.
        """
        message = "Server does not exist"
        failure_body = {"itemNotFound": {"message": message, "code": 404}}

        dispatcher = EQFDispatcher([(
            intent,
            service_request_eqf(
                stub_pure_response(json.dumps(failure_body), 404)))])

        with self.assertRaises(NoSuchServerError) as cm:
            sync_perform(dispatcher, effect)

        self.assertEqual(
            cm.exception,
            NoSuchServerError(message, server_id=six.text_type(server_id)))

    def assert_handles_nova_rate_limiting(self, intent, effect):
        """
        If the provided intent returns a response consistent with Nova
        rate-limiting requests, then performing the effect will raise a
        :class:`NovaRateLimitError`.
        """
        failure_body = {
            "overLimit": {
                "code": 413,
                "message": "OverLimit Retry...",
                "details": "Error Details...",
                "retryAfter": "2015-02-27T23:42:27Z"
            }
        }
        dispatcher = EQFDispatcher([(
            intent,
            service_request_eqf(
                stub_pure_response(json.dumps(failure_body), 413)))])

        with self.assertRaises(NovaRateLimitError) as cm:
            sync_perform(dispatcher, effect)

        self.assertEqual(cm.exception,
                         NovaRateLimitError("OverLimit Retry..."))

    def assert_handles_nova_compute_fault(self, intent, effect):
        """
        If the provided intent returns a response consistent with a Nova
        compute fault error, then performing the request will raise a
        :class:`NovaComputeFaultError`
        """
        failure_body = {
            "computeFault": {
                "code": 500,
                "message": ("The server has either erred or is incapable of "
                            "performing the requested operation."),
            }
        }
        with self.assertRaises(NovaComputeFaultError) as cm:
            _perform_one_request(intent, effect, 500, json.dumps(failure_body))

        self.assertEqual(
            cm.exception,
            NovaComputeFaultError(
                "The server has either erred or is incapable of performing "
                "the requested operation."))

    def test_set_nova_metadata_item_success(self):
        """
        Produce a request setting a metadata item on a Nova server, which
        returns a successful result on 200.
        """
        server_id, expected, real = self._setup_for_set_nova_metadata_item()
        body = {"meta": {"k": "v"}}

        seq = [
            (expected.intent,
             service_request_eqf(stub_pure_response(json.dumps(body), 200))),
            (log_intent('request-set-metadata-item', body), lambda _: None)
        ]
        resp, response_json = perform_sequence(seq, real)
        self.assertEqual(resp, StubResponse(200, {}))
        self.assertEqual(response_json, body)

    def test_set_nova_metadata_item_too_many_metadata_items(self):
        """
        Raises a :class:`ServerMetadataOverLimitError` if there are too many
        metadata items on a server.
        """
        server_id, expected, real = self._setup_for_set_nova_metadata_item()

        message = "Maximum number of metadata items exceeds 40"
        failure_body = {"forbidden": {"message": message, "code": 403}}

        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(
                stub_pure_response(json.dumps(failure_body), 403)))])

        with self.assertRaises(ServerMetadataOverLimitError) as cm:
            sync_perform(dispatcher, real)

        self.assertEqual(
            cm.exception,
            ServerMetadataOverLimitError(message,
                                         server_id=six.text_type(server_id)))

    def test_set_nova_metadata_item_standard_errors(self):
        """
        Raise a :class:`NoSuchServerError` if the server doesn't exist.
        Raise a :class:`NovaRateLimitError` if Nova starts rate-limiting
        requests.
        Raise a :class:`NovaComputeFaultError` if Nova fails.
        """
        server_id, expected, eff = self._setup_for_set_nova_metadata_item()
        self.assert_handles_no_such_server(expected.intent, eff, server_id)
        self.assert_handles_nova_compute_fault(expected.intent, eff)

    def _setup_for_get_server_details(self):
        """
        Produce the data needed to test :obj:`get_server_details`: a tuple
        of (server_id, expected_effect, real_effect)
        """
        server_id = unicode(uuid4())
        real = get_server_details(server_id=server_id)
        expected = service_request(
            ServiceType.CLOUD_SERVERS,
            'GET',
            'servers/{0}'.format(server_id),
            success_pred=has_code(200))
        return (server_id, expected, real)

    def test_get_server_details_success(self):
        """
        Produce a request getting a Nova server's details, which
        returns a successful result on 200.
        """
        server_id, expected, real = self._setup_for_get_server_details()
        body = {"so much": "data"}
        seq = [
            (expected.intent,
             service_request_eqf(stub_pure_response(json.dumps(body), 200))),
            (log_intent('request-one-server-details', body), lambda _: None)
        ]
        resp, response_json = perform_sequence(seq, real)
        self.assertEqual(resp, StubResponse(200, {}))
        self.assertEqual(response_json, body)

    def test_get_server_details_errors(self):
        """
        Correctly parses nova rate limiting errors, no such server errors, and
        compute fault errors.
        """
        server_id, expected, eff = self._setup_for_get_server_details()
        self.assert_handles_no_such_server(expected.intent, eff, server_id)
        self.assert_handles_nova_rate_limiting(expected.intent, eff)
        self.assert_handles_nova_compute_fault(expected.intent, eff)

    def _setup_for_create_server(self):
        """
        Produce the data needed to test :obj:`create_server`: a tuple of
        (expected_effect, real_effect)
        """
        real = create_server({'server': 'args'})
        expected = service_request(
            ServiceType.CLOUD_SERVERS,
            'POST', 'servers',
            data={'server': 'args'},
            reauth_codes=(401,),
            success_pred=has_code(202))
        return (expected, real)

    def test_create_server_success(self):
        """
        Creating a server, when Nova responds with a 202, returns Nova's
        response with the body as a JSON dictionary.  It logs this response
        minus the adminstrative password.
        """
        server_body = {'server': {'id': 'server_id', 'adminPass': "12345"}}
        log_intent = Log('request-create-server', {
            'url': "original/request/URL",
            'method': 'method',
            'request_id': "original-request-id",
            'response_body': '{"server": {"id": "server_id"}}',
            'request_body': ''
        })
        expected, real = self._setup_for_create_server()
        resp, body = _perform_one_request(
            expected.intent, real, 202,
            json.dumps(server_body), log_intent)
        self.assertEqual(body, server_body)

    def test_create_server_standard_errors(self):
        """
        Creating a server correctly parses nova rate limiting errors and
        compute fault errors.
        """
        expected, real = self._setup_for_create_server()
        self.assert_handles_nova_rate_limiting(expected.intent, real)
        self.assert_handles_nova_compute_fault(expected.intent, real)

    def test_create_server_configuration_errors(self):
        """
        Correctly parses user configuration errors.
        """
        def _plaintext(msg, extra=""):
            body = "".join((
                "403 Forbidden\n\n",
                "Access was denied to this resource.\n\n ",
                msg + extra))
            return (403, body, msg)

        def _badrequest(msg):
            return (
                400,
                json.dumps({'badRequest': {'message': msg, 'code': 400}}),
                msg)

        bad_configs = [
            _badrequest("Invalid key_name provided."),
            _plaintext(
                "Networks (00000000-0000-0000-0000-000000000000,"
                "11111111-1111-1111-1111-111111111111) required but missing"),
            _plaintext(
                "Networks (00000000-0000-0000-0000-000000000000) not allowed"),
            _plaintext("Exactly 1 isolated network(s) must be attached"),
            _plaintext("Exactly 1 isolated network(s) must be attached", " ")]

        expected, real = self._setup_for_create_server()

        for code, body, msg in bad_configs:
            with self.assertRaises(CreateServerConfigurationError) as cm:
                _perform_one_request(expected.intent, real, code, body)
            self.assertEqual(cm.exception, CreateServerConfigurationError(msg))

        # similar, but wrong, error messages are unparsed
        unparseable = [
            (403, json.dumps(
                {'badRequest': {'message': 'Invalid key_name provided',
                                'code': 400}})),
            (400, json.dumps({"no": {'message': 'Invalid key_name provided',
                                     'code': 400}})),
            _plaintext("I don't like your networks")[:2]
        ]
        for code, body in unparseable:
            with self.assertRaises(APIError):
                _perform_one_request(expected.intent, real, code, body)

    def test_create_server_quota_errors(self):
        """
        Correctly parses over quota errors.
        """
        quotas = [
            ("Quota exceeded for ram: Requested 1024, but already used 131072 "
             "of 131072 ram"),
            ("Quota exceeded for instances: Requested 1, but already used "
             "100 of 100 instances"),
            ("Quota exceeded for onmetal-compute-v1-instances: Requested 1, "
             "but already used 10 of 10 onmetal-compute-v1-instances"),
        ]

        expected, real = self._setup_for_create_server()

        for msg in quotas:
            with self.assertRaises(CreateServerOverQuoteError) as cm:
                _perform_one_request(expected.intent, real, 403,
                                     json.dumps({'forbidden': {'message': msg,
                                                               'code': 403}}))
            self.assertEqual(cm.exception, CreateServerOverQuoteError(msg))

        # similar, but wrong, error messages are unparsed
        unparseable = [
            (403, json.dumps({'forbiddin': {'message': quotas[0],
                                            'code': 403}})),
            (402, json.dumps({'forbidden': {'message': quotas[0],
                                            'code': 403}})),
            (403, quotas[0])
        ]
        for code, body in unparseable:
            with self.assertRaises(APIError):
                _perform_one_request(expected.intent, real, code, body)

    def _list_server_details_intent(self, params):
        """Return the expected intent for listing servers given parameters."""
        return service_request(
            ServiceType.CLOUD_SERVERS,
            'GET', 'servers/detail',
            params=params).intent

    def _list_server_details_log_intent(self, body):
        """Return a :obj:`Log` intent for listing server details."""
        return log_intent('request-list-servers-details', body, False)

    def test_list_servers_details_page(self):
        """
        :func:`list_servers_details_page` returns the JSON response from
        listing servers details.
        """
        params = {'limit': ['100'], 'marker': ['1']}
        body = {'servers': [], 'servers_links': []}
        eff = list_servers_details_page(params)
        expected_intent = self._list_server_details_intent(params)
        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(json.dumps(body), 200))),
            (self._list_server_details_log_intent(body), lambda _: None)
        ]
        resp, response_json = perform_sequence(seq, eff)
        self.assertEqual(response_json, body)

        self.assert_handles_nova_compute_fault(expected_intent, eff)
        self.assert_handles_nova_rate_limiting(expected_intent, eff)

    def test_list_servers_details_all_gets_until_no_next_link(self):
        """
        :func:`list_servers_details_all` follows the servers links until there
        are no more links, and returns a list of servers as the result.  It
        ignores any non-next links.
        """
        bodies = [
            {'servers': ['1', '2'],
             'servers_links': [{'href': 'doesnt_matter_url?marker=3',
                                'rel': 'next'}]},
            {'servers': ['3', '4'],
             'servers_links': [{'href': 'doesnt_matter_url?marker=5',
                                'rel': 'next'},
                               {'href': 'doesnt_matter_url?marker=1',
                                'rel': 'prev'}]},
            {'servers': ['5', '6'],
             'servers_links': [{'href': 'doesnt_matter_url?marker=3',
                                'rel': 'prev'}]}
        ]
        resps = [json.dumps(d) for d in bodies]

        eff = list_servers_details_all({'marker': ['1']})
        seq = [
            (self._list_server_details_intent({'marker': ['1']}),
             service_request_eqf(stub_pure_response(resps[0], 200))),
            (self._list_server_details_log_intent(bodies[0]), lambda _: None),
            (self._list_server_details_intent({'marker': ['3']}),
             service_request_eqf(stub_pure_response(resps[1], 200))),
            (self._list_server_details_log_intent(bodies[1]), lambda _: None),
            (self._list_server_details_intent({'marker': ['5']}),
             service_request_eqf(stub_pure_response(resps[2], 200))),
            (self._list_server_details_log_intent(bodies[2]), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, ['1', '2', '3', '4', '5', '6'])

    def test_list_servers_details_all_blows_up_if_got_same_link_twice(self):
        """
        :func:`list_servers_details_all` raises an exception if Nova returns
        the same next link twice in a row.
        """
        bodies = [
            {'servers': ['1', '2'],
             'servers_links': [{'href': 'doesnt_matter_url?marker=3',
                                'rel': 'next'}]},
            {'servers': ['3', '4'],
             'servers_links': [{'href': 'doesnt_matter_url?marker=3',
                                'rel': 'next'},
                               {'href': 'doesnt_matter_url?marker=1',
                                'rel': 'prev'}]}
        ]
        resps = [json.dumps(d) for d in bodies]

        eff = list_servers_details_all({'marker': ['1']})
        seq = [
            (self._list_server_details_intent({'marker': ['1']}),
             service_request_eqf(stub_pure_response(resps[0], 200))),
            (self._list_server_details_log_intent(bodies[0]), lambda _: None),
            (self._list_server_details_intent({'marker': ['3']}),
             service_request_eqf(stub_pure_response(resps[1], 200))),
            (self._list_server_details_log_intent(bodies[1]), lambda _: None)
        ]
        self.assertRaises(NovaComputeFaultError, perform_sequence, seq, eff)

    def test_list_servers_details_all_propagates_errors(self):
        """
        :func:`list_servers_details_all` propagates exceptions from making
        the individual requests (from :func:`list_servers_details_page`).
        """
        eff = list_servers_details_all({'marker': ['1']})
        seq = [
            (self._list_server_details_intent({'marker': ['1']}),
             lambda _: raise_(NovaComputeFaultError('error')))
        ]
        self.assertRaises(NovaComputeFaultError, perform_sequence, seq, eff)


class CloudOrchestrationTests(SynchronousTestCase):
    """
    Tests for cloud orchestration functions.
    """
    def _list_stacks_all_intent(self, params):
        """Return the expected intent for listing stacks given parameters."""
        return service_request(
            ServiceType.CLOUD_ORCHESTRATION,
            'GET', 'stacks',
            reauth_codes=(401,),
            params=params).intent

    def _create_stack_intent(self, data):
        return service_request(
            ServiceType.CLOUD_ORCHESTRATION,
            'POST', 'stacks',
            data=data,
            success_pred=has_code(201),
            reauth_codes=(401,)).intent

    def _check_stack_intent(self, stack_name, stack_id):
        return service_request(
            ServiceType.CLOUD_ORCHESTRATION,
            'POST', 'stacks/{0}/{1}/actions'.format(stack_name, stack_id),
            data={'check': None},
            success_pred=has_code(200, 201),
            reauth_codes=(401,),
            json_response=False).intent

    def _update_stack_intent(self, stack_name, stack_id, stack_args):
        return service_request(
            ServiceType.CLOUD_ORCHESTRATION,
            'PUT', 'stacks/{0}/{1}'.format(stack_name, stack_id),
            data=stack_args,
            success_pred=has_code(202),
            reauth_codes=(401,),
            json_response=False).intent

    def _delete_stack_intent(self, stack_name, stack_id):
        return service_request(
            ServiceType.CLOUD_ORCHESTRATION,
            'DELETE', 'stacks/{0}/{1}'.format(stack_name, stack_id),
            success_pred=has_code(204),
            reauth_codes=(401,),
            json_response=False).intent

    def test_list_stacks_all(self):
        """
        :func:`list_stacks_all` returns the JSON response from listing stacks.
        """
        body = {'stacks': ['foo', 'bar']}
        eff = list_stacks_all()
        expected_intent = self._list_stacks_all_intent(None)
        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(json.dumps(body), 200))),
            (log_intent('request-list-stacks-all', body), lambda _: None)
        ]
        stacks = perform_sequence(seq, eff)
        self.assertEqual(stacks, ['foo', 'bar'])

    def test_create_stack(self):
        """Create stack calls Heat and returns the new stack details on 201."""
        data = {'data': 'data'}
        body = {'stack': 'the_stack_json'}
        eff = create_stack(data)
        expected_intent = self._create_stack_intent(data)
        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(json.dumps(body), 201))),
            (log_intent('request-create-stack', body), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, 'the_stack_json')

    def test_check_stack_200(self):
        """Check stack calls Heat and returns None on a 200."""
        stack_name = 'foostack'
        stack_id = 'foo_id'
        eff = check_stack(stack_name, stack_id)
        expected_intent = self._check_stack_intent(stack_name, stack_id)

        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response('200!', 200))),
            (log_intent('request-check-stack', '200!', False), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, None)

    def test_check_stack_201(self):
        """Check stack calls Heat and returns None on a 201."""
        stack_name = 'foostack'
        stack_id = 'foo_id'
        eff = check_stack(stack_name, stack_id)
        expected_intent = self._check_stack_intent(stack_name, stack_id)

        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(b'', 201))),
            (log_intent('request-check-stack', b'', False), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, None)

    def test_update_stack(self):
        """Update stack calls Heat and returns None on a 202."""
        stack_name = 'foostack'
        stack_id = 'foo_id'
        stack_args = {'stack': 'data'}
        eff = update_stack(stack_name, stack_id, stack_args)
        expected_intent = self._update_stack_intent(stack_name, stack_id,
                                                    stack_args)
        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(b'', 202))),
            (log_intent('request-update-stack', b'', False), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, None)

    def test_update_stack_with_response_body(self):
        """Update stack succeeds even if there is content in the response."""
        stack_name = 'foostack'
        stack_id = 'foo_id'
        stack_args = {'stack': 'data'}
        eff = update_stack(stack_name, stack_id, stack_args)
        expected_intent = self._update_stack_intent(stack_name, stack_id,
                                                    stack_args)
        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response('xyz', 202))),
            (log_intent('request-update-stack', 'xyz', False), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, None)

    def test_delete_stack(self):
        """Delete stack calls Heat and returns None on a 204."""
        stack_name = 'foostack'
        stack_id = 'foo_id'
        eff = delete_stack(stack_name, stack_id)
        expected_intent = self._delete_stack_intent(stack_name, stack_id)

        seq = [
            (expected_intent,
             service_request_eqf(stub_pure_response(b'', 204))),
            (log_intent('request-delete-stack', b'', False), lambda _: None)
        ]
        result = perform_sequence(seq, eff)
        self.assertEqual(result, None)
