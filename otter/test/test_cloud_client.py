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
from effect.testing import EQFDispatcher

import mock

import six

from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import Authenticate, InvalidateToken
from otter.cloud_client import (
    CLBDeletedError,
    CLBPendingUpdateError,
    CLBRateLimitError,
    NoSuchCLBError,
    NoSuchCLBNodeError,
    NoSuchServerError,
    NovaRateLimitError,
    ServerMetadataOverLimitError,
    ServiceRequest,
    TenantScope,
    add_bind_service,
    change_clb_node,
    concretize_service_request,
    get_cloud_client_dispatcher,
    get_server_details,
    perform_tenant_scope,
    service_request,
    set_nova_metadata_item,
    _Throttle,
    _make_default_throttler,
    _perform_throttle,
    _serialize_and_delay)
from otter.constants import ServiceType
from otter.test.utils import (
    StubResponse,
    resolve_effect,
    stub_pure_response)
from otter.test.worker.test_launch_server_v1 import fake_service_catalog
from otter.util.http import APIError, headers
from otter.util.pure_http import Request, has_code


fake_service_configs = {
    ServiceType.CLOUD_SERVERS: {
        'name': 'cloudServersOpenStack',
        'region': 'DFW'},
    ServiceType.CLOUD_LOAD_BALANCERS: {
        'name': 'cloudLoadBalancers',
        'region': 'DFW'}
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
            service_configs=fake_service_configs,
            throttler=lambda stype, url: None,
            tenant_id='000000',
            service_request=service_request_intent)

        # "authenticate"
        eff = resolve_authenticate(eff)
        # make request
        return resolve_effect(eff, stub_response)

    return resolve_service_request


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
        self.service_configs = {
            ServiceType.CLOUD_SERVERS: {
                'name': 'cloudServersOpenStack',
                'region': 'DFW'},
            ServiceType.CLOUD_LOAD_BALANCERS: {
                'name': 'cloudLoadBalancers',
                'region': 'DFW'}
        }
        eff = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        self.svcreq = eff.intent

    def _concrete(self, svcreq, **kwargs):
        """
        Call :func:`concretize_service_request` with premade test objects.
        """
        return concretize_service_request(
            self.authenticator, self.log, self.service_configs,
            lambda stype, url: None,
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


class SerializeAndDelayTests(SynchronousTestCase):
    """Tests for :func:`_serialize_and_delay`."""

    @mock.patch('otter.cloud_client.DeferredLock')
    def test_serialize_and_delay(self, deferred_lock):
        """
        :func:`_serialize_and_delay` returns a function that, when given a
        function and arguments, calls it inside of a lock and after a specified
        delay.
        """
        class DeferredLock(object):
            def run(self, f, *args, **kwargs):
                return f(*args, **kwargs).addCallback(lambda r: ('locked', r))
        deferred_lock.side_effect = DeferredLock

        clock = Clock()
        bracket = _serialize_and_delay(clock, 15)

        result = bracket(lambda: succeed('foo'))
        clock.advance(14)
        self.assertNoResult(result)
        clock.advance(15)
        self.assertEqual(self.successResultOf(result), ('locked', 'foo'))


class MakeDefaultThrottleTests(SynchronousTestCase):
    """Tests for :func:`_make_default_throttler`."""

    def test_mismatch(self):
        """policy doesn't have a throttler for random junk."""
        throttler = _make_default_throttler(None)
        self.assertIs(throttler("foo", "get"), None)

    def test_post_cloud_servers(self):
        """POSTs to cloud servers get throttled by a second."""
        clock = Clock()
        throttler = _make_default_throttler(clock)
        bracket = throttler(ServiceType.CLOUD_SERVERS, 'post')
        d = bracket(lambda: 'foo')
        self.assertNoResult(d)
        clock.advance(1)
        self.assertEqual(self.successResultOf(d), 'foo')

    def test_delete_cloud_servers(self):
        """DELETEs to cloud servers get throttled by a second."""
        clock = Clock()
        throttler = _make_default_throttler(clock)
        bracket = throttler(ServiceType.CLOUD_SERVERS, 'delete')
        d = bracket(lambda: 'foo')
        self.assertNoResult(d)
        clock.advance(1)
        self.assertEqual(self.successResultOf(d), 'foo')

    def test_post_and_delete_not_the_same(self):
        """
        The throttlers for POST and DELETE to cloud servers are different.
        """
        clock = Clock()
        throttler = _make_default_throttler(clock)
        deleter = throttler(ServiceType.CLOUD_SERVERS, 'delete')
        poster = throttler(ServiceType.CLOUD_SERVERS, 'post')
        self.assertIsNot(deleter, poster)


class GetCloudClientDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_cloud_client_dispatcher`."""

    def test_performs_throttle(self):
        """:func:`_perform_throttle` performs :obj:`_Throttle`."""
        dispatcher = get_cloud_client_dispatcher(None, None, None, None)
        throttle = _Throttle(bracket=lambda f, *a, **kw: f(*a, **kw),
                             effect=Effect(Constant('foo')))
        self.assertIs(dispatcher(throttle), _perform_throttle)

    def test_performs_tenant_scope(self):
        """:func:`perform_tenant_scope` performs :obj:`TenantScope`"""
        1 / 0


class PerformTenantScopeTests(SynchronousTestCase):
    """Tests for :func:`perform_tenant_scope`."""

    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.service_configs = {
            ServiceType.CLOUD_SERVERS: {
                'name': 'cloudServersOpenStack',
                'region': 'DFW'}
        }

        self.throttler = lambda stype, url: None

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


class CLBClientTests(SynchronousTestCase):
    """
    Tests for CLB client functions, such as :obj:`change_clb_node`.
    """
    @property
    def lb_id(self):
        """What is my LB ID"""
        return u"123456"

    def assert_parses_common_clb_errors(self, intent, eff):
        """
        Assert that the effect produced performs the common CLB error parsing:
        :class:`CLBPendingUpdateError`, :class:`CLBDescription`,
        :class:`NoSuchCLBError`, :class:`CLBRateLimitError`,
        :class:`APIError`
        """
        json_responses_and_errs = [
            ("Load Balancer '{0}' has a status of 'PENDING_UPDATE' and is "
             "considered immutable.", 422, CLBPendingUpdateError),
            ("Load Balancer '{0}' has a status of 'PENDING_DELETE' and is "
             "considered immutable.", 422, CLBDeletedError),
            ("The load balancer is deleted and considered immutable.",
             422, CLBDeletedError),
            ("Load balancer not found.", 404, NoSuchCLBError),
            ("OverLimit Retry...", 413, CLBRateLimitError)
        ]

        for msg, code, err in json_responses_and_errs:
            msg = msg.format(self.lb_id)
            resp = stub_pure_response(
                json.dumps({'message': msg, 'code': code, 'details': ''}),
                code)
            with self.assertRaises(err) as cm:
                sync_perform(
                    EQFDispatcher([(intent, service_request_eqf(resp))]),
                    eff)
            self.assertEqual(cm.exception, err(msg, lb_id=self.lb_id))

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
            stub_pure_response("random repose error message", 404),
            stub_pure_response("random repose error message", 413)
        ]

        for resp in bad_resps:
            with self.assertRaises(APIError) as cm:
                sync_perform(
                    EQFDispatcher([(intent, service_request_eqf(resp))]),
                    eff)
            self.assertEqual(
                cm.exception,
                APIError(headers={}, code=resp[0].code, body=resp[1]))

    def test_change_clb_node(self):
        """
        Produce a request for modifying a load balancer, which returns a
        successful result on 202.

        Parse the common CLB errors, and :class:`NoSuchCLBNodeError`.
        """
        eff = change_clb_node(lb_id=self.lb_id, node_id=u'1234',
                              condition="DRAINING", weight=50)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            'loadbalancers/{0}/nodes/1234'.format(self.lb_id),
            data={'condition': 'DRAINING',
                  'weight': 50},
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
            NoSuchCLBNodeError(msg, lb_id=self.lb_id, node_id=u'1234'))

        # all the common failures
        self.assert_parses_common_clb_errors(expected.intent, eff)


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
        existing, then performing the effect will return a
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
        rate-limiting requests, then performing the effect will return a
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

    def test_set_nova_metadata_item_success(self):
        """
        Produce a request setting a metadata item on a Nova server, which
        returns a successful result on 200.
        """
        server_id, expected, real = self._setup_for_set_nova_metadata_item()

        success_body = {"meta": {"k": "v"}}
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(
                stub_pure_response(json.dumps(success_body), 200)))])

        self.assertEqual(sync_perform(dispatcher, real),
                         (StubResponse(200, {}), success_body))

    def test_set_nova_metadata_item_too_many_metadata_items(self):
        """
        Return a :class:`ServerMetadataOverLimitError` if there are too many
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

    def test_set_nova_metadata_item_no_such_server(self):
        """
        Return a :class:`NoSuchServerError` if the server doesn't exist.
        """
        server_id, expected, eff = self._setup_for_set_nova_metadata_item()
        self.assert_handles_no_such_server(expected.intent, eff, server_id)

    def test_set_nova_metadata_rate_limiting(self):
        """
        Return a :class:`NovaRateLimitError` if Nova starts rate-limiting
        requests.
        """
        server_id, expected, eff = self._setup_for_set_nova_metadata_item()
        self.assert_handles_nova_rate_limiting(expected.intent, eff)

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

        success_body = {"so much": "data"}
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(
                stub_pure_response(json.dumps(success_body), 200)))])

        self.assertEqual(sync_perform(dispatcher, real),
                         (StubResponse(200, {}), success_body))

    def test_get_server_details_errors(self):
        """
        Correctly parses nova rate limiting errors and no such server errors.
        """
        server_id, expected, eff = self._setup_for_get_server_details()
        self.assert_handles_no_such_server(expected.intent, eff, server_id)
        self.assert_handles_nova_rate_limiting(expected.intent, eff)
