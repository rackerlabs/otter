"""Tests for otter.util.pure_http"""

import json

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from testtools import TestCase
from testtools.matchers import raises

from effect.testing import StubIntent, resolve_effect, resolve_stub, fail_effect, resolve_stubs, StubErrorIntent, FuncIntent
from effect.twisted import perform
from effect import Effect

from otter.util.pure_http import request, Request, ReauthFailedError, retry
from otter.util.http import APIError, headers
from otter.test.utils import stub_pure_response, StubResponse, StubTreq


class RequestEffectTests(SynchronousTestCase):
    """
    Tests for the effects of pure_http.Request.
    """
    def test_perform(self):
        """
        The Request effect dispatches a request to treq, and returns a two-tuple
        of the Twisted Response object and the content as bytes.
        """
        response = StubResponse(200, {})
        treq = StubTreq(
            reqs={('GET', 'http://google.com/', None, None, None): succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="get", url="http://google.com/")
        req.treq = treq
        self.assertEqual(
            self.successResultOf(perform(Effect(req))),
            (response, "content"))

    def test_post(self):
        """The Request effect supports non-GET methods as well."""
        response = StubResponse(200, {})
        treq = StubTreq(
            reqs={('POST', 'http://google.com/', (('foo', 'bar'),), 'my data', None):
                  succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="post", url="http://google.com/", headers={'foo': 'bar'},
                      data='my data')
        req.treq = treq
        self.assertEqual(self.successResultOf(perform(Effect(req))),
                         (response, "content"))

    def test_log(self):
        """
        The log specified in the Request is passed on to the treq implementation.
        """
        response = StubResponse(200, {})
        log = object()
        treq = StubTreq(
            reqs={('GET', 'http://google.com/', None, None, log): succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="get", url="http://google.com/", log=log)
        req.treq = treq
        self.assertEqual(self.successResultOf(perform(Effect(req))),
                         (response, "content"))


class PureHTTPClientTests(TestCase):
    """Tests for the pure HTTP client functions."""

    def _no_reauth_client(self):
        def auth(refresh=False):
            assert not refresh
            return Effect(StubIntent("my-token"))
        return lambda *args, **kwargs: resolve_stub(request(*args, auth=auth, **kwargs))

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
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}))
        result = resolve_effect(eff, stub_result)
        self.assertEqual(result, {"foo": "bar"})

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
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}), code=404)
        self.assertRaises(APIError, resolve_effect, eff, stub_result)

    def test_api_error_specified(self):
        """Any HTTP response code can be specified as being successful."""
        request_ = self._no_reauth_client()
        eff = request_("get", url="/foo", success_codes=[404])
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}), code=404)
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
        reauth_effect = Effect(StubIntent("new-token"))

        def auth(refresh=False):
            if refresh:
                return reauth_effect
            else:
                return Effect(StubIntent("first-token"))
        # First we try to make a simple request.
        kwargs = {}
        if reauth_codes is not None:
            kwargs['reauth_codes'] = reauth_codes
        eff = request("get", "/foo", auth=auth, **kwargs)
        # The initial (cached) token is retrieved.
        eff = resolve_stub(eff)

        # Reauthentication is then triggered:
        stub_result = stub_pure_response("badauth!", code=code)
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(reauth_effect_result.intent, reauth_effect.intent)

        # And the original HTTP response (of whatever code) is returned.
        api_error = self.assertRaises(APIError, resolve_stub, reauth_effect_result)
        self.assertEqual(api_error.code, code)
        self.assertEqual(api_error.body, "badauth!")
        self.assertEqual(api_error.headers, {})


class RetryTests(TestCase):

    def test_should_not_retry(self):
        """retry raises the last error if should_retry returns False."""
        result = retry(Effect(StubErrorIntent(RuntimeError("oh no!"))),
                       lambda e: Effect(StubIntent(False)))
        self.assertThat(lambda: resolve_stubs(result),
                        raises(RuntimeError("oh no!")))


    def _repeated_effect_func(self, *funcs):
        """
        Return an (impure) function which does different things based on the
        number of times it's been called.
        """
        counter = [0]
        def func():
            count = counter[0]
            counter[0] += 1
            return funcs[count]()
        return func


    def test_retry(self):
        """
        When should_retry returns an Effect of True, the func will be called
        again.
        """
        func = self._repeated_effect_func(
          lambda: raise_(RuntimeError("foo")),
          lambda: "final")
        result = retry(Effect(FuncIntent(func)),
                       lambda e: Effect(StubIntent(True)))
        self.assertEqual(resolve_stubs(result), "final")

    def test_continue_retrying(self):
        """
        should_retry is passed the exception information, and will be
        called until it returns False.
        """

        func = self._repeated_effect_func(
            lambda: raise_(RuntimeError("1")),
            lambda: raise_(RuntimeError("2")),
            lambda: raise_(RuntimeError("3")))

        def should_retry(e):
            return Effect(StubIntent(str(e[1]) != "3"))

        result = retry(Effect(FuncIntent(func)), should_retry)
        self.assertThat(lambda: resolve_stubs(result),
                        raises(RuntimeError("3")))


def raise_(exc):
    raise exc
