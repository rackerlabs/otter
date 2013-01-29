"""
Unittests for the launch_server_v1 launch config.
"""

import mock

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed
from twisted.web.http_headers import Headers

from otter.worker.launch_server_v1 import (
    APIError,
    check_success,
    append_segments,
    auth_headers
)


class UtilityTestCase(TestCase):
    """
    Tests for non-specific utilities that should be refactored out of the worker
    implementation eventually.
    """

    def setUp(self):
        """
        set up test dependencies for utilities.
        """
        self.treq_patcher = mock.patch('otter.worker.launch_server_v1.treq')
        self.treq = self.treq_patcher.start()
        self.addCleanup(self.treq_patcher.stop)

    def test_api_error(self):
        """
        An APIError will be instantiated with an HTTP Code and an HTTP response
        body and will expose these in public attributes and have a reasonable
        string representation.
        """
        e = APIError(404, "Not Found.")

        self.assertEqual(e.code, 404)
        self.assertEqual(e.body, "Not Found.")
        self.assertEqual(str(e), "API Error code=404, body='Not Found.'")

    def test_check_success(self):
        """
        check_success will return the response if the response.code is in success_codes.
        """
        response = mock.Mock()
        response.code = 201

        self.assertEqual(check_success(response, [200, 201]), response)

    def test_check_success_non_success_code(self):
        """
        check_success will return a deferred that errbacks with an APIError
        if the response.code is not in success_codes.
        """
        response = mock.Mock()
        response.code = 404
        self.treq.content.return_value = succeed('Not Found.')

        d = check_success(response, [200, 201])
        f = self.failureResultOf(d)

        self.assertTrue(f.check(APIError))
        self.assertEqual(f.value.code, 404)
        self.assertEqual(f.value.body, 'Not Found.')

    def test_append_segments(self):
        """
        append_segments will append an arbitrary number of path segments to
        a base url even if there is a trailing / on the base uri.
        """
        expected = 'http://example.com/foo/bar/baz'
        self.assertEqual(
            append_segments('http://example.com', 'foo', 'bar', 'baz'),
            expected
        )

        self.assertEqual(
            append_segments('http://example.com/', 'foo', 'bar', 'baz'),
            expected
        )

    def test_append_segments_unicode(self):
        """
        append_segments will convert to utf-8 and quote unicode path segments.
        """
        self.assertEqual(
            append_segments('http://example.com', u'\u2603'),
            'http://example.com/%E2%98%83'
        )

    def test_append_segments_quote(self):
        """
        append_segments will quote all path segments.
        """
        self.assertEqual(
            append_segments('http://example.com', 'foo bar'),
            'http://example.com/foo%20bar'
        )

    def test_auth_headers_content_type(self):
        """
        auth_headers will use a json content-type.
        """
        self.assertEqual(
            auth_headers('any')['content-type'], ['application/json'])

    def test_auth_headers_accept(self):
        """
        auth_headers will use a json accept header.
        """
        self.assertEqual(
            auth_headers('any')['accept'], ['application/json'])

    def test_auth_headers_sets_auth_token(self):
        """
        auth_headers will set the X-Auth-Token header based on it's auth_token
        argument.
        """
        self.assertEqual(
            auth_headers('my-auth-token')['x-auth-token'], ['my-auth-token'])

    def test_auth_headers_can_be_http_headers(self):
        """
        auth_headers will produce a result that can be passed to
        twisted.web.http_headers.Headers.
        """
        headers = Headers(auth_headers('my-auth-token'))
        self.assertIsInstance(headers, Headers)
