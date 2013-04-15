"""
Tests for ``otter.util``
"""
from datetime import datetime
import mock

from twisted.trial.unittest import TestCase

from otter.util.http import append_segments
from otter.util.hashkey import generate_capability
from otter.util import timestamp, config


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


class TimestampTests(TestCase):
    """
    Test timestamp utilities
    """
    @mock.patch('otter.util.timestamp.datetime', spec=['utcnow'])
    def test_now_returns_iso8601Z_timestamp_no_microseconds(self, mock_datetime):
        """
        ``now()`` returns the current UTC time in iso8601 zulu format
        """
        mock_datetime.utcnow.return_value = datetime(
            2000, 01, 01, 12, 0, 0, 0, None)
        self.assertEqual(timestamp.now(), "2000-01-01T12:00:00Z")

    @mock.patch('otter.util.timestamp.datetime', spec=['utcnow'])
    def test_now_returns_iso8601Z_timestamp_microseconds(self, mock_datetime):
        """
        ``now()`` returns the current UTC time in iso8601 zulu format
        """
        mock_datetime.utcnow.return_value = datetime(
            2000, 01, 01, 12, 0, 0, 111111, None)
        self.assertEqual(timestamp.now(), "2000-01-01T12:00:00.111111Z")

    def test_min_returns_iso8601Z_timestamp(self):
        """
        datetime.min returns the earliest available time:
        ``datetime(MINYEAR, 1, 1, tzinfo=None)`` according to the docs.  ``MIN``
        returns this datetime in iso8601 zulu format.
        """
        self.assertEqual(timestamp.MIN, "0001-01-01T00:00:00Z")

    @mock.patch('otter.util.timestamp.datetime', spec=['utcnow'])
    def test_from_timestamp_can_read_now_timestamp(self, mock_datetime):
        """
        ``from_timestamp`` can parse timestamps produced by ``now()``
        """
        mock_datetime.utcnow.return_value = datetime(
            2000, 01, 01, 12, 0, 0, 0, None)

        parsed = timestamp.from_timestamp(timestamp.now())

        # can't compare naive and timestamp-aware datetimes, so check that
        # the parsed timezone is not None.  Then replace with None to compare.
        self.assertTrue(parsed.tzinfo is not None)
        self.assertEqual(parsed.replace(tzinfo=None),
                         mock_datetime.utcnow.return_value)

    def test_from_timestamp_can_read_min_timestamp(self):
        """
        ``from_timestamp`` can parse timestamps produced by ``MIN``
        """
        parsed = timestamp.from_timestamp(timestamp.MIN)

        # can't compare naive and timestamp-aware datetimes, so check that
        # the parsed timezone is not None.  Then replace with None to compare.
        self.assertTrue(parsed.tzinfo is not None)
        self.assertEqual(parsed.replace(tzinfo=None), datetime.min)


class ConfigTest(TestCase):
    """
    Test the simple configuration API.
    """
    def setUp(self):
        """
        Set up a basic configuration dictionary.
        """
        config.set_config_data({
            'foo': 'bar',
            'baz': {'bax': 'quux'}
        })

    def test_top_level_value(self):
        """
        config_value returns the value stored at the top level key.
        """
        self.assertEqual(config.config_value('foo'), 'bar')

    def test_nested_value(self):
        """
        config_value returns the value stored at a . separated path.
        """
        self.assertEqual(config.config_value('baz.bax'), 'quux')

    def test_non_existent_value(self):
        """
        config_value will return None if the path does not exist in the
        nested dictionaries.
        """
        self.assertIdentical(config.config_value('baz.blah'), None)
