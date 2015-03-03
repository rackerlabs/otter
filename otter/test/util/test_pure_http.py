"""Tests for otter.util.pure_http"""

import json
from itertools import starmap

from effect import Constant, Effect, Func
from effect.testing import Stub
from effect.twisted import perform

from testtools import TestCase

from twisted.trial.unittest import SynchronousTestCase

from otter.effect_dispatcher import get_simple_dispatcher
from otter.test.utils import (
    StubResponse, StubTreq, resolve_stubs, stub_pure_response)
from otter.util.http import APIError
from otter.util.pure_http import (
    Request,
    add_bind_root,
    add_content_only,
    add_effect_on_response,
    add_effectful_headers,
    add_error_handling,
    add_headers,
    add_json_request_data,
    add_json_response,
    check_response,
    effect_on_response,
    has_code,
    request,
)


ESConstant = lambda x: Effect(Stub(Constant(x)))


def stub_request(response):
    """Create a request function that returns a stubbed response."""
    return lambda method, url, headers=None, data=None: ESConstant(response)


class RequestEffectTests(SynchronousTestCase):
    """
    Tests for the effects of pure_http.Request.
    """
    def test_perform(self):
        """
        The Request effect dispatches a request to treq, and returns a
        two-tuple of the Twisted Response object and the content as bytes.
        """
        req = ('GET', 'http://google.com/', None, None, None, {'log': None})
        response = StubResponse(200, {})
        treq = StubTreq(reqs=[(req, response)],
                        contents=[(response, "content")])
        req = Request(method="get", url="http://google.com/")
        req.treq = treq
        dispatcher = get_simple_dispatcher(None)
        self.assertEqual(
            self.successResultOf(perform(dispatcher, Effect(req))),
            (response, "content"))

    def test_log(self):
        """
        The log specified in the Request is passed on to the treq
        implementation.
        """
        log = object()
        req = ('GET', 'http://google.com/', None, None, None, {'log': log})
        response = StubResponse(200, {})
        treq = StubTreq(reqs=[(req, response)],
                        contents=[(response, "content")])
        req = Request(method="get", url="http://google.com/", log=log)
        req.treq = treq
        dispatcher = get_simple_dispatcher(None)
        self.assertEqual(
            self.successResultOf(perform(dispatcher, Effect(req))),
            (response, "content"))


class AddErrorHandlingTests(SynchronousTestCase):
    """Tests :func:`add_error_handling`."""
    def test_error(self):
        """
        :func:`add_error_handling` ostensibly invokes :func:`check_response`.
        """
        response = stub_pure_response("", code=404)
        request_fn = add_error_handling(has_code(200), stub_request(response))
        eff = request_fn('GET', '/xyzzy')
        self.assertRaises(APIError, resolve_stubs, eff)


class CheckResponseTests(SynchronousTestCase):
    """Tests :func:`check_response`."""
    def test_error(self):
        """
        :func:`check_response` raises :class:`APIError` if the predicate
        doesn't like the response.
        """
        pred = lambda _response, _content: False
        result = stub_pure_response(None)
        self.assertRaises(APIError, check_response, pred, result)

    def test_success(self):
        """
        :func:`check_response` returns the value passed into it if the
        predicate likes the response.
        """
        pred = lambda _response, _content: True
        result = stub_pure_response(None)
        self.assertIdentical(check_response(pred, result), result)


class HasCodeTests(SynchronousTestCase):
    """Tests :func:`has_code`."""

    def test_has_code(self):
        """
        The predicate returns :data:`True` if the given response is in the
        successful code list, :data:`False` otherwise.
        """
        pred = has_code(200, 204)

        def check_for_code(code):
            return pred(*stub_pure_response(None, code))

        self.assertTrue(check_for_code(200))
        self.assertTrue(check_for_code(204))
        self.assertFalse(check_for_code(400))
        self.assertFalse(check_for_code(500))

    def test_equality(self):
        """
        Return values from multiple calls to :func:`has_code` have correct
        equality semantics.
        """
        a, b, c, d = starmap(has_code, [(200,), (200,), (200, 204), (400,)])

        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)
        self.assertNotEqual(b, c)
        self.assertNotEqual(b, d)
        self.assertNotEqual(c, d)

    def test_introspection(self):
        """
        The codes are introspectable.
        """
        self.assertEqual(has_code(200, 300, 400).codes, (200, 300, 400))


class AddEffectfulHeadersTest(TestCase):
    """
    Tests for :func:`add_effectful_headers`.
    """

    def setUp(self):
        """Save auth effect."""
        super(AddEffectfulHeadersTest, self).setUp()
        self.auth_effect = ESConstant({"x-auth-token": "abc123"})

    def test_add_headers(self):
        """Headers from the provided effect are inserted."""
        request_ = add_effectful_headers(self.auth_effect, request)
        eff = request_('m', 'u', headers={'default': 'headers'})
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method="m",
                    url="u",
                    headers={"x-auth-token": "abc123",
                             "default": "headers"}))

    def test_added_headers_win(self):
        """When merging headers together, headers from the effect win."""
        request_ = add_effectful_headers(self.auth_effect, request)
        eff = request_('m', 'u', headers={'x-auth-token': 'fooey'})
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method="m",
                    url="u",
                    headers={"x-auth-token": "abc123"}))

    def test_add_headers_optional(self):
        """It's okay if no headers are passed."""
        request_ = add_effectful_headers(self.auth_effect, request)
        eff = request_('m', 'u')
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method='m',
                    url='u',
                    headers={'x-auth-token': 'abc123'}))


class AddHeadersTest(TestCase):
    """Tests for :func:`add_headers`."""

    def test_add_headers(self):
        """Headers are merged, with passed headers taking precedence."""
        request_ = add_headers({'one': '1', 'two': '2'}, request)
        eff = request_('m', 'u', headers={'one': 'hey', 'three': '3'})
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method='m',
                    url='u',
                    headers={'one': 'hey', 'two': '2', 'three': '3'}))

    def test_add_headers_optional(self):
        """It's okay if no headers are passed."""
        request_ = add_headers({'one': '1'}, request)
        eff = request_('m', 'u')
        self.assertEqual(
            resolve_stubs(eff).intent,
            Request(method='m',
                    url='u',
                    headers={'one': '1'}))


class EffectOnResponseTests(TestCase):
    """Tests for :func:`effect_on_response`."""

    def setUp(self):
        """Set up an invalidation request ."""
        super(EffectOnResponseTests, self).setUp()
        self.invalidations = []
        invalidate = lambda: self.invalidations.append(True)
        self.invalidate_effect = Effect(Stub(Func(invalidate)))

    def test_invalidate(self):
        """
        :func:`effect_on_response` invokes the provided effect and
        returns an Effect of the original response.
        """
        badauth = stub_pure_response("badauth!", code=401)
        eff = effect_on_response((401,), self.invalidate_effect, badauth)
        self.assertEqual(eff.intent, self.invalidate_effect.intent)
        self.assertEqual(resolve_stubs(eff), badauth)
        self.assertEqual(self.invalidations, [True])

    def test_invalidate_unnecessary(self):
        """
        The result is returned immediately and the provided effect is not
        invoked when the HTTP response code is not in ``codes``.
        """
        good = stub_pure_response("okay!", code=200)
        result = effect_on_response((401,), self.invalidate_effect, good)
        self.assertEqual(result, good)
        self.assertEqual(self.invalidations, [])

    def test_add_effect_on_response(self):
        """Test the decorator :func:`add_effect_on_response`."""
        badauth = stub_pure_response("badauth!", code=401)
        request_ = add_effect_on_response(
            self.invalidate_effect, (401,), stub_request(badauth))
        eff = request_('m', 'u')
        self.assertEqual(resolve_stubs(eff), badauth)
        self.assertEqual(self.invalidations, [True])


class BindRootTests(TestCase):
    """Tests for :func:`add_bind_root`"""

    def test_bind_root(self):
        """
        :func:`add_bind_root` decorates a request function to append any
        passed URL paths onto the root URL.
        """
        request_ = add_bind_root("http://slashdot.org/", request)
        self.assertEqual(request_("get", "foo").intent.url,
                         "http://slashdot.org/foo")

    def test_bind_root_no_slashes(self):
        """
        Root URLs without a trailing slash will have one inserted
        automatically.
        """
        request_ = add_bind_root("http://slashdot.org", request)
        self.assertEqual(request_("get", "foo").intent.url,
                         "http://slashdot.org/foo")

    def test_bind_root_does_not_quote(self):
        """
        Appending URL is not quoted
        """
        request_ = add_bind_root("http://slashdot.org", request)
        self.assertEqual(request_("get", "foo~").intent.url,
                         "http://slashdot.org/foo~")

    def test_root_unicode(self):
        """
        If root is unicode, it is encoded as ascii before appending
        """
        request_ = add_bind_root(u'http://example.com', request)
        self.assertEqual(request_("get", "foo").intent.url,
                         "http://example.com/foo")

    def test_url_unicode(self):
        """
        If url is unicode, it is encoded as utf-8 before appending
        """
        request_ = add_bind_root('http://example.com', request)
        self.assertEqual(request_("get", u"foo\u0100").intent.url,
                         "http://example.com/foo\xc4\x80")


class ContentOnlyTests(TestCase):
    """Tests for :func:`add_content_only`"""

    def test_add_content_only(self):
        """The produced request function results in the content."""
        request_ = add_content_only(stub_request(stub_pure_response('foo', 200)))
        eff = request_('m', 'u')
        self.assertEqual(resolve_stubs(eff), 'foo')


class AddJsonResponseTests(TestCase):
    """Tests for :func:`add_json_response`."""
    def test_add_json_response(self):
        """The produced request function results in a parsed data structure."""
        response = stub_pure_response('{"a": "b"}', 200)
        request_ = add_json_response(stub_request(response))
        self.assertEqual(resolve_stubs(request_('m', 'u')),
                         (response[0], {'a': 'b'}))

    def test_empty_json_response(self):
        """
        If the body is empty, it will be turned into :data:`None`, and not
        passed to the JSON parser.
        """
        response = stub_pure_response('', 204)
        request_ = add_json_response(stub_request(response))
        self.assertEqual(resolve_stubs(request_('m', 'u')),
                         (response[0], None))


class AddJsonRequestDataTests(TestCase):
    """Tests for :func:`add_json_request_data`."""
    def test_add_json_request_data(self):
        """The produced request function serializes data to json."""
        eff = add_json_request_data(request)('m', 'u', data={'a': 'b'})
        self.assertEqual(eff.intent.data, json.dumps({'a': 'b'}))
