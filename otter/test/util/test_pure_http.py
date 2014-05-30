"""Tests for otter.util.pure_http"""

import json

from twisted.trial.unittest import TestCase

from effect.testing import (StubRequest, get_request,
                            resolve_effect, resolve_stub)
from effect import Effect

from otter.util.pure_http import OSHTTPClient, Request, ReauthIneffectualError
from otter.util.http import APIError
from otter.test.utils import StubResponse


class RequestEffectTests(TestCase):
    """
    Tests for the effects of pure_http.Request.
    """
    pass


class OSHTTPClientTests(TestCase):
    """Tests for OSHTTPClient."""
    # test reauth required, reauth failed, ReauthIneffectualError

    def test_json_request(self):
        """
        The request we pass in is performed after adding some standard headers.
        """
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        # - unit tests want to know about all the true effects that need to be
        #   performed
        # - unit tests do NOT want to know about how implementation organizes
        #   its callbacks
        # get_effect_request(eff) -> innermost effect request
        # resolve_effect(eff, result) -> invokes callbacks, innermost to outer,
        # and returns the result. If any callback returns an Effect, further callbacks
        # will not be run, and instead a new effect is returned.
        req = get_request(eff)
        self.assertEqual(req.method, "get")
        self.assertEqual(req.url, "/foo")
        self.assertIs(req.data, None)
        self.assertEqual(
            req.headers,
            {'User-Agent': ['OtterScale/0.0'],
             'accept': ['application/json'],
             'content-type': ['application/json'],
             'x-auth-token': ['my-token']})

    def test_json_response(self):
        """The JSON response is decoded into Python objects."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        stub_result = (StubResponse(200, {}), json.dumps({"foo": "bar"}))
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
        req = get_request(eff)
        self.assertEqual(
            req.headers,
            {'User-Agent': ['OtterScale/0.0'],
             'accept': ['application/json'],
             'content-type': ['application/json'],
             'x-auth-token': ['my-token'],
             'x-mine': 'abc123'})

    def test_data(self):
        """The data member in the request is passed through untouched."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request(
            "my-token",
            Request(method="get", url="/foo", data="foo"))
        req = get_request(eff)
        self.assertEqual(req.data, "foo")

    def test_api_error_default(self):
        """
        APIError is raised when the response code isn't 200, by default.
        """
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"))
        stub_result = (StubResponse(404, {}), json.dumps({"foo": "bar"}))
        self.assertRaises(APIError, resolve_effect, eff, stub_result)

    def test_api_error_specified(self):
        """Any HTTP response code can be specified as being successful."""
        http = OSHTTPClient(lambda: 1 / 0)
        eff = http.json_request("my-token", Request(method="get", url="/foo"),
                                success=[404])
        stub_result = (StubResponse(404, {}), json.dumps({"foo": "bar"}))
        self.assertEqual(resolve_effect(eff, stub_result), {"foo": "bar"})

    def test_reauth_successful(self):
        """
        When an HTTP response code is 401, the reauth function is invoked.
        When the reauth function's effect succeeds, the original request is
        retried with the x-auth-token header updated to use the new auth
        token.
        """
        reauth_effect = Effect(StubRequest("new-token"))
        http = OSHTTPClient(lambda: reauth_effect)
        # 1. First we try to make a simple request, but it returns 401:
        eff = http.json_request("first-token",
                                Request(method="get", url="/foo"))
        stub_result = (StubResponse(401, {}), "")
        # 2. Reauthentication is then triggered:
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(get_request(reauth_effect_result), reauth_effect.request)
        # 3. When retry succeeds, the original request is retried:
        retry_eff = resolve_stub(reauth_effect_result)
        retry_req = get_request(retry_eff)
        # The x-auth-token header has been updated
        self.assertEqual(
            retry_req.headers,
            {'User-Agent': ['OtterScale/0.0'],
             'accept': ['application/json'],
             'content-type': ['application/json'],
             'x-auth-token': ['new-token']})

        # The final request's result is returned as the ultimate result of the
        # original effect
        stub_response = (StubResponse(200, {}), '{"result": 1}')
        final_result = resolve_effect(retry_eff, stub_response)
        self.assertEqual(final_result, {'result': 1})

    def test_ineffectual_reauth(self):
        """
        When a 401 is returned even after reauthentication, ReauthIneffectualError is
        raised.
        """
        reauth_effect = Effect(StubRequest("new-token"))
        http = OSHTTPClient(lambda: reauth_effect)
        # 1. First we try to make a simple request, but it returns 401:
        eff = http.json_request("first-token",
                                Request(method="get", url="/foo"))
        stub_result = (StubResponse(401, {}), "")
        # 2. Reauthentication is then triggered:
        reauth_effect_result = resolve_effect(eff, stub_result)
        self.assertIs(get_request(reauth_effect_result), reauth_effect.request)
        # 3. When retry succeeds, the original request is retried:
        retry_eff = resolve_stub(reauth_effect_result)
        retry_req = get_request(retry_eff)
        # When 401 is returned *again*, we get the error.
        stub_response = (StubResponse(401, {}), '{"result": 1}')
        self.assertRaises(ReauthIneffectualError,
                          resolve_effect, retry_eff, stub_response)
