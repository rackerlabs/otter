import json

from twisted.trial.unittest import TestCase

from effect.testing import StubRequest, serialize, get_request, resolve_effect

from otter.util.pure_http import OSHTTPClient, Request
from otter.test.utils import StubResponse


class RequestEffectTests(TestCase):
    pass


class OSHTTPClientTests(TestCase):
    # test no reauth required, 404 (bad status code), APIError
    # test reauth required, reauth succeeded, 200, parsed json, everything cool
    # test reauth required, reauth failed, ReauthenticationFailed

    def test_json_request(self):
        http = OSHTTPClient(lambda: 1/0)
        eff = http.json_request("my-token", Request("get", "/foo"))
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
        http = OSHTTPClient(lambda: 1/0)
        eff = http.json_request("my-token", Request("get", "/foo"))
        stub_result = (StubResponse(200, {}), json.dumps({"foo": "bar"}))
        result = resolve_effect(eff, stub_result)
        self.assertEqual(result, {"foo": "bar"})

    def test_header_merging(self):
        """
        The headers passed in the original request are merged with a
        pre-defined set.
        """
        http = OSHTTPClient(lambda: 1/0)
        eff = http.json_request(
            "my-token",
            Request("get", "/foo", headers={"x-mine": "abc123"}))
        req = get_request(eff)
        self.assertEqual(
            req.headers,
            {'User-Agent': ['OtterScale/0.0'],
             'accept': ['application/json'],
             'content-type': ['application/json'],
             'x-auth-token': ['my-token'],
             'x-mine': 'abc123'})
