"""Tests for otter.http."""

import json
from functools import partial

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    TypeDispatcher,
    base_dispatcher,
    sync_perform)
from effect.testing import resolve_effect

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import Authenticate, InvalidateToken
from otter.constants import ServiceType
from otter.http import (
    ServiceRequest,
    TenantScope,
    add_bind_service,
    concretize_service_request,
    get_request_func,
    perform_tenant_scope,
    service_request)
from otter.test.utils import stub_pure_response
from otter.test.worker.test_launch_server_v1 import fake_service_catalog
from otter.util.http import APIError, headers
from otter.util.pure_http import Request, has_code


def resolve_authenticate(eff, token='token'):
    """Resolve an Authenticate effect with test data."""
    return resolve_effect(eff, (token, fake_service_catalog))


class GetRequestFuncTests(SynchronousTestCase):
    """
    Tests for :func:`get_request_func`.

    These are duplicates of the tests for :obj:`ServiceRequest`. When
    everything is switched over to that, :func:`get_request_func` and these
    tests should be deleted.
    """

    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.request_func = get_request_func(
            self.authenticator, 1, self.log,
            {ServiceType.CLOUD_SERVERS: 'cloudServersOpenStack'},
            'DFW')

    def test_get_request_func_authenticates(self):
        """
        The request function returned from get_request_func performs
        authentication before making the request.
        """
        eff = self.request_func(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
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
        eff = self.request_func(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        next_eff = resolve_authenticate(eff)
        # When the HTTP response is an auth error, the auth cache is
        # invalidated, by way of the next effect:
        invalidate_eff = resolve_effect(next_eff, stub_pure_response("", 401))
        expected_intent = InvalidateToken(self.authenticator, 1)
        self.assertEqual(invalidate_eff.intent, expected_intent)
        self.assertRaises(APIError, resolve_effect, invalidate_eff, None)

    def test_json(self):
        """
        JSON-serializable requests are dumped before being sent, and
        JSON-serialized responses are parsed.
        """
        input_json = {"a": 1}
        output_json = {"b": 2}
        eff = self.request_func(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                data=input_json)
        next_eff = resolve_authenticate(eff)
        result = resolve_effect(next_eff,
                                stub_pure_response(json.dumps(output_json)))
        self.assertEqual(next_eff.intent.data, json.dumps(input_json))
        self.assertEqual(result, output_json)

    def test_no_json_response(self):
        """
        ``json_response`` can be set to :data:`False` to get the plaintext.
        response.
        """
        eff = self.request_func(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                json_response=False)
        next_eff = resolve_authenticate(eff)
        result = resolve_effect(next_eff, stub_pure_response("foo"))
        self.assertEqual(result, "foo")


class BindServiceTests(SynchronousTestCase):
    """Tests for :func:`add_bind_service`."""

    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.request_func = lambda method, url, headers=None, data=None: (method, url, headers, data)

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
                    log=None,
                    reauth_codes=(401, 403),
                    success_pred=has_code(200),
                    json_response=True,
                )
            )
        )


class PerformServiceRequestTests(SynchronousTestCase):
    """Tests for :func:`concretize_service_request`."""
    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.service_mapping = {
            ServiceType.CLOUD_SERVERS: 'cloudServersOpenStack'}
        eff = service_request(ServiceType.CLOUD_SERVERS, 'GET', 'servers')
        self.svcreq = eff.intent

    def _concrete(self, svcreq):
        """
        Call :func:`concretize_service_request` with premade test objects.
        """
        return concretize_service_request(
            self.authenticator, self.log, self.service_mapping, 'DFW',
            1,
            svcreq
        )

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
        result = resolve_effect(next_eff,
                                stub_pure_response(json.dumps(output_json)))
        self.assertEqual(result, output_json)

    def test_no_json_response(self):
        """
        ``json_response`` can be set to :data:`False` to get the plaintext.
        response.
        """
        svcreq = service_request(ServiceType.CLOUD_SERVERS, "GET", "servers",
                                 json_response=False).intent
        eff = self._concrete(svcreq)
        next_eff = resolve_authenticate(eff)
        result = resolve_effect(next_eff, stub_pure_response("foo"))
        self.assertEqual(result, "foo")


class PerformTenantScopeTests(SynchronousTestCase):
    """Tests for :func:`perform_tenant_scope`."""

    def setUp(self):
        """Save some common parameters."""
        self.log = object()
        self.authenticator = object()
        self.service_mapping = {
            ServiceType.CLOUD_SERVERS: 'cloudServersOpenStack'}

        def concretize(au, lo, smap, reg, tenid, srvreq):
            return Effect(Constant(('concretized', au, lo, smap, reg, tenid,
                                    srvreq)))

        self.dispatcher = ComposedDispatcher([
            TypeDispatcher({
                TenantScope: partial(perform_tenant_scope, self.authenticator,
                                     self.log, self.service_mapping, 'DFW',
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
            ('concretized', self.authenticator, self.log, self.service_mapping,
             'DFW', 1, ereq.intent))

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
            ('concretized', self.authenticator, self.log, self.service_mapping,
             'DFW', 1, ereq.intent))
