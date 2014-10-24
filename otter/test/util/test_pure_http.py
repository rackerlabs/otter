"""Tests for otter.util.pure_http"""

from twisted.trial.unittest import SynchronousTestCase

from testtools import TestCase

from effect.testing import StubIntent, resolve_stubs
from effect.twisted import perform
from effect import Effect, ConstantIntent, FuncIntent

from otter.util.pure_http import (
    request_with_auth, Request, check_status, bind_root, get_request)
from otter.util.http import APIError
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


class CheckStatusTests(TestCase):
    """Tests :func:`check_status`"""

    def test_check_status(self):
        """
        :func:`check_status` raises an APIError when HTTP codes don't match.
        """
        self.assertRaises(
            APIError,
            check_status,
            (200,),
            stub_pure_response({"foo": "bar"}, code=404))

    def test_check_status_success(self):
        """When the HTTP code matches, the response is returned."""
        response = stub_pure_response({"foo": "bar"}, code=404)
        result = check_status((404,),  response)
        self.assertEqual(result, response)


class RequestWithAuthTests(TestCase):
    """Tests for :func:`request_with_auth`"""

    def setUp(self):
        """Save auth and invalidate effects."""
        super(RequestWithAuthTests, self).setUp()
        self.invalidations = []
        invalidate = lambda: self.invalidations.append(True)
        self.auth_effect = Effect(Constant({"x-auth-token": "abc123"}))
        self.invalidate_effect = Effect(StubIntent(FuncIntent(invalidate)))

    def test_header_merging(self):
        """
        The headers passed in the original request are merged with
        authentication headers.
        """
        eff = request_with_auth(
            lambda headers: get_request("m", "u", headers=headers),
            self.auth_effect,
            self.invalidate_effect,
            headers={"default": "headers"})
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method="m",
                    url="u",
                    headers={"x-auth-token": "abc123",
                             "default": "headers"}))

    def test_auth_headers_win(self):
        """
        When merging headers together, auth headers win.
        """
        eff = request_with_auth(
            lambda headers: get_request("m", "u", headers=headers),
            self.auth_effect,
            self.invalidate_effect,
            headers={"x-auth-token": "fooey"})
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method="m",
                    url="u",
                    headers={"x-auth-token": "abc123"}))

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
        # First we try to make a simple request.
        kwargs = {}
        if reauth_codes is not None:
            kwargs['reauth_codes'] = reauth_codes
        badauth = stub_pure_response("badauth!", code=code)
        eff = request_with_auth(
            lambda headers: badauth,
            self.auth_effect,
            self.invalidate_effect,
            headers={"base": "header"},
            **kwargs)
        self.assertEqual(resolve_stubs(eff), badauth)
        self.assertEqual(self.invalidations, [True])


class BindRootTests(TestCase):
    """Tests for :func:`bind_root`"""

    def test_bind_root(self):
        """
        :func:`bind_root` returns a new request function that appends any
        passed URL paths onto the root URL.
        """
        request = bind_root(get_request, "http://slashdot.org/")
        self.assertEqual(request("get", "foo").intent.url,
                         "http://slashdot.org/foo")
