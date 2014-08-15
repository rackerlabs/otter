"""Tests for otter.util.pure_http"""

from twisted.trial.unittest import SynchronousTestCase

from testtools import TestCase

from effect.testing import StubIntent, resolve_effect, resolve_stubs
from effect.twisted import perform
from effect import Effect, ConstantIntent

from otter.util.pure_http import request, Request
from otter.util.http import APIError, headers
from otter.test.utils import stub_pure_response, StubResponse, StubTreq


Constant = lambda x: StubIntent(ConstantIntent(x))


class RequestEffectTests(SynchronousTestCase):
    """
    Tests for the effects of pure_http.Request.
    """
    def test_perform(self):
        """
        The Request effect dispatches a request to treq, and returns a two-tuple
        of the Twisted Response object and the content as bytes.
        """
        req = ('GET', 'http://google.com/', None, None,  {'log': None})
        response = StubResponse(200, {})
        treq = StubTreq(reqs=[(req, response)],
                        contents=[(response, "content")])
        req = Request(method="get", url="http://google.com/")
        req.treq = treq
        self.assertEqual(
            self.successResultOf(perform(Effect(req))),
            (response, "content"))

    def test_log(self):
        """
        The log specified in the Request is passed on to the treq implementation.
        """
        log = object()
        req = ('GET', 'http://google.com/', None, None, {'log': log})
        response = StubResponse(200, {})
        treq = StubTreq(reqs=[(req, response)],
                        contents=[(response, "content")])
        req = Request(method="get", url="http://google.com/", log=log)
        req.treq = treq
        self.assertEqual(self.successResultOf(perform(Effect(req))),
                         (response, "content"))


class PureHTTPClientTests(TestCase):
    """Tests for the pure HTTP client functions."""

    def _no_reauth_client(self):
        def auth(refresh=False):
            assert not refresh
            return Effect(Constant(headers("my-token")))
        return lambda *args, **kwargs: resolve_stubs(request(*args, auth=auth, **kwargs))

    def test_json_request(self):
        """
        The request we pass in is performed after adding some standard headers.
        """
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo")
        req = eff.intent
        self.assertEqual(req.method, "get")
        self.assertEqual(req.url, "/foo")
        self.assertIs(req.data, None)
        self.assertEqual(req.headers, headers('my-token'))

    def test_json_response(self):
        """The JSON response is decoded into Python objects."""
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo")
        self.assertEqual(
            resolve_effect(eff, stub_pure_response({"foo": "bar"})),
            {'foo': 'bar'})

    def test_header_merging(self):
        """
        The headers passed in the original request are merged with a
        pre-defined set.
        """
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo", headers={"x-mine": "abc123"})
        req = eff.intent
        expected_headers = headers('my-token')
        expected_headers['x-mine'] = 'abc123'
        self.assertEqual(req.headers, expected_headers)

    def test_default_headers_win(self):
        """
        When merging headers together, the predefined set takes precedent
        over any that are passed.
        """
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo", headers={"x-auth-token": "abc123"})
        req = eff.intent
        expected_headers = headers('my-token')
        self.assertEqual(req.headers, expected_headers)

    def test_data(self):
        """The data member in the request is encoded with json."""
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo", data={'foo': 'bar'})
        req = eff.intent
        self.assertEqual(req.data, '{"foo": "bar"}')

    def test_api_error_default(self):
        """
        APIError is raised when the response code isn't 200, by default.
        """
        request_ = self._no_reauth_client()
        eff = request_("get", "/foo")
        self.assertRaises(
            APIError,
            resolve_effect, eff,
            stub_pure_response({"foo": "bar"}, code=404))

    def test_api_error_specified(self):
        """Any HTTP response code can be specified as being successful."""
        request_ = self._no_reauth_client()
        eff = request_("get", url="/foo", success_codes=[404])
        stub_result = stub_pure_response({"foo": "bar"}, code=404)
        self.assertEqual(resolve_effect(eff, stub_result), {"foo": "bar"})

    def test_reauth_successful(self):
        """
        When an HTTP response code is 401, the reauth function is invoked.
        When the reauth function's effect succeeds, the original request is
        retried with the x-auth-token header updated to use the new auth
        token.
        """
        return self._test_reauth(401)

    def test_reauth_on_403(self):
        """
        Reauthentication also automatically happens on a 403 response.
        """
        return self._test_reauth(403)

    def test_reauth_on_custom_code(self):
        """
        Reauthentication can happen on other codes too.
        """
        return self._test_reauth(500, reauth_codes=(401, 403, 500))

    def _test_reauth(self, code, reauth_codes=None):
        reauth_effect = Effect(Constant(headers("new-token")))

        def auth(refresh=False):
            if refresh:
                return reauth_effect
            else:
                return Effect(Constant(headers("first-token")))
        # First we try to make a simple request.
        kwargs = {}
        if reauth_codes is not None:
            kwargs['reauth_codes'] = reauth_codes
        eff = request("get", "/foo", auth=auth, **kwargs)

        # The initial (cached) token is retrieved.
        eff = resolve_stubs(eff)

        # Reauthentication is then triggered:
        stub_result = stub_pure_response("badauth!", code=code)
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(reauth_effect_result.intent, reauth_effect.intent)

        # And the original HTTP response (of whatever code) is returned.
        api_error = self.assertRaises(APIError, resolve_stubs, reauth_effect_result)
        self.assertEqual(api_error.code, code)
        self.assertEqual(api_error.body, "badauth!")
        self.assertEqual(api_error.headers, {})
