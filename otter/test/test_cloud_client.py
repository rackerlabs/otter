"""Tests for otter.cloud_client"""

import json
from functools import partial

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    TypeDispatcher,
    base_dispatcher,
    sync_perform)
from effect.testing import EQFDispatcher

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import Authenticate, InvalidateToken
from otter.cloud_client import (
    CLBDeletedError,
    CLBPendingUpdateError,
    CLBRateLimitError,
    NoSuchCLBError,
    NoSuchCLBNodeError,
    ServiceRequest,
    TenantScope,
    add_bind_service,
    change_clb_node,
    concretize_service_request,
    perform_tenant_scope,
    service_request)
from otter.constants import ServiceType
from otter.test.utils import (
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
            self.authenticator, self.log, self.service_configs, 1, svcreq,
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

        def concretize(au, lo, smap, tenid, srvreq):
            return Effect(Constant(('concretized', au, lo, smap, tenid,
                                    srvreq)))

        self.dispatcher = ComposedDispatcher([
            TypeDispatcher({
                TenantScope: partial(perform_tenant_scope, self.authenticator,
                                     self.log, self.service_configs,
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
             1, ereq.intent))

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
             1, ereq.intent))


class CLBClientTests(SynchronousTestCase):
    """
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
