from twisted.trial.unittest import TestCase

from otter.utils.pure_http import OSHTTPClient, Request

from effect.testing import StubRequest


class RequestEffectTests(TestCase):
    pass


class OSHTTPClientTests(TestCase):
    # test no reauth required, 200, parsed json, everything cool
    # test no reauth required, 404 (bad status code), APIError
    # test reauth required, reauth succeeded, 200, parsed json, everything cool
    # test reauth required, reauth failed, ReauthenticationFailed

    def test_json_request(self):
        http = OSHTTPClient(lambda: 1/0)
        eff = http.json_request("my-token", Request("get", "/foo"))