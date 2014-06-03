"""Tests for otter.util.pure_http"""

import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed
from twisted.trial.unittest import TestCase

from effect.testing import StubIntent, resolve_effect, resolve_stub
from effect import Effect

from otter.util.pure_http import OSHTTPClient, Request, ReauthIneffectualError, conj
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
            gets={('http://google.com/', None, None, None): succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="get", url="http://google.com/")
        self.assertEqual(
            self.successResultOf(req.perform_effect({}, treq=treq)),
            (response, "content"))

    def test_post(self):
        """
        treq dispatches to the appropriate treq method based on the method
        specified in the Request.
        """
        response = StubResponse(200, {})
        treq = StubTreq(
            posts={('http://google.com/', (('foo', 'bar'),), 'my data', None):
                   succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="post", url="http://google.com/", headers={'foo': 'bar'},
                      data='my data')
        self.assertEqual(self.successResultOf(req.perform_effect({}, treq=treq)),
                         (response, "content"))

    def test_log(self):
        """
        The log specified in the Request is passed on to the treq implementation.
        """
        response = StubResponse(200, {})
        log = object()
        treq = StubTreq(
            gets={('http://google.com/', None, None, log): succeed(response)},
            contents={response: succeed("content")})
        req = Request(method="get", url="http://google.com/", log=log)
        self.assertEqual(self.successResultOf(req.perform_effect({}, treq=treq)),
                         (response, "content"))


class OSHTTPClientTests(TestCase):
    """Tests for OSHTTPClient."""

    def test_json_request(self):
        """
        The request we pass in is performed after adding some standard headers.
        """
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        req = eff.intent
        self.assertEqual(req.method, "get")
        self.assertEqual(req.url, "/foo")
        self.assertIs(req.data, None)
        self.assertEqual(req.headers, headers('my-token'))

    def test_json_response(self):
        """The JSON response is decoded into Python objects."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}))
        result = resolve_effect(eff, stub_result)
        self.assertEqual(result, {"foo": "bar"})

    def test_header_merging(self):
        """
        The headers passed in the original request are merged with a
        pre-defined set.
        """
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request(
            "my-token",
            Request(method="get", url="/foo", headers={"x-mine": "abc123"}))
        req = eff.intent
        self.assertEqual(req.headers, conj(headers('my-token'),
                                           {'x-mine': 'abc123'}))

    def test_data(self):
        """The data member in the request is passed through untouched."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request(
            "my-token",
            Request(method="get", url="/foo", data="foo"))
        req = eff.intent
        self.assertEqual(req.data, "foo")

    def test_api_error_default(self):
        """
        APIError is raised when the response code isn't 200, by default.
        """
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}), code=404)
        self.assertRaises(APIError, resolve_effect, eff, stub_result)

    def test_api_error_specified(self):
        """Any HTTP response code can be specified as being successful."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"),
                                success=[404])
        stub_result = stub_pure_response(json.dumps({"foo": "bar"}), code=404)
        self.assertEqual(resolve_effect(eff, stub_result), {"foo": "bar"})

    def test_reauth_successful(self):
        """
        When an HTTP response code is 401, the reauth function is invoked.
        When the reauth function's effect succeeds, the original request is
        retried with the x-auth-token header updated to use the new auth
        token.
        """
        reauth_effect = Effect(StubIntent("new-token"))
        http = OSHTTPClient(lambda: reauth_effect)
        # 1. First we try to make a simple request, but it returns 401:
        eff = http.json_request("first-token",
                                Request(method="get", url="/foo"))
        stub_result = stub_pure_response("", code=401)
        # 2. Reauthentication is then triggered:
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(reauth_effect_result.intent, reauth_effect.intent)
        # 3. When retry succeeds, the original request is retried:
        retry_eff = resolve_stub(reauth_effect_result)
        retry_req = retry_eff.intent
        # The x-auth-token header has been updated
        self.assertEqual(retry_req.headers, headers('new-token'))

        # The final request's result is returned as the ultimate result of the
        # original effect
        stub_response = stub_pure_response('{"result": 1}')
        final_result = resolve_effect(retry_eff, stub_response)
        self.assertEqual(final_result, {'result': 1})

    def test_ineffectual_reauth(self):
        """
        When a 401 is returned even after reauthentication, ReauthIneffectualError is
        raised.
        """
        reauth_effect = Effect(StubIntent("new-token"))
        http = OSHTTPClient(lambda: reauth_effect)
        # 1. First we try to make a simple request, but it returns 401:
        eff = http.json_request("first-token",
                                Request(method="get", url="/foo"))
        stub_result = stub_pure_response("", code=401)
        # 2. Reauthentication is then triggered:
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(reauth_effect_result.intent, reauth_effect.intent)
        # 3. When retry succeeds, the original request is retried:
        retry_eff = resolve_stub(reauth_effect_result)
        # When 401 is returned *again*, we get the error.
        stub_response = stub_pure_response("", code=401)
        self.assertRaises(ReauthIneffectualError,
                          resolve_effect, retry_eff, stub_response)
