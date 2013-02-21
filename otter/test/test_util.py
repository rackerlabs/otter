"""
Tests for ``otter.util``
"""

from twisted.trial.unittest import TestCase

from otter.util.http import append_segments


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
