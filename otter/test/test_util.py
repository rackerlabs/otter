"""
Tests for ``otter.util``
"""
import mock

from twisted.trial.unittest import TestCase

from otter.util.http import append_segments
from otter.util.hashkey import generate_capability


class HTTPUtilityTests(TestCase):
    """
    Tests for ``otter.util.http``
    """
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


class CapabilityTests(TestCase):
    """
    Test capability generation.
    """
    @mock.patch('otter.util.hashkey.os.urandom')
    def test_urandom_32_bytes(self, urandom):
        """
        generate_capability will use os.urandom to get 32 bytes of random
        data.
        """
        (_v, _cap) = generate_capability()
        urandom.assert_called_once_with(32)

    @mock.patch('otter.util.hashkey.os.urandom')
    def test_hex_encoded_cap(self, urandom):
        """
        generate_capability will hex encode the random bytes from os.urandom.
        """
        urandom.return_value = '\xde\xad\xbe\xef'
        (_v, cap) = generate_capability()
        self.assertEqual(cap, 'deadbeef')

    def test_version_1(self):
        """
        generate_capability returns a version 1 capability.
        """
        (v, _cap) = generate_capability()
        self.assertEqual(v, "1")
