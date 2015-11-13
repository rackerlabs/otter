"""
Tests for ``otter.util``
"""
from datetime import datetime
import mock
import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed, fail, Deferred
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.web.http_headers import Headers

from otter.log.bound import BoundLog
from otter.test.utils import (
    DummyException, IsBoundWith, LockMixin, matches, mock_log, patch)
from otter.util import config, timestamp
from otter.util.deferredutils import TimedOutError, delay, with_lock
from otter.util.hashkey import generate_capability
from otter.util.http import (
    APIError,
    RequestError,
    UpstreamError,
    append_segments,
    check_success,
    headers,
    raise_error_on_code,
    retry_on_unauth,
    try_json_with_keys,
    wrap_request_error)


class HTTPUtilityTests(SynchronousTestCase):
    """
    Tests for ``otter.util.http``
    """
    def setUp(self):
        """
        set up test dependencies for utilities.
        """
        self.treq = patch(self, 'otter.util.http.treq')

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

    def test_append_segments_unicode_uri(self):
        """
        append_segments will convert a uri to an ascii bytestring if it is
        a unicode object.
        """

        self.assertEqual(
            append_segments(u'http://example.com', 'foo'),
            'http://example.com/foo'
        )

    def test_append_segments_quote(self):
        """
        append_segments will quote all path segments.
        """
        self.assertEqual(
            append_segments('http://example.com', 'foo bar'),
            'http://example.com/foo%20bar'
        )

    def test_api_error(self):
        """
        An APIError will be instantiated with an HTTP Code, an HTTP response
        body, and HTTP headers, and will expose these in public attributes and
        have a reasonable string representation.
        """
        e = APIError(404, "Not Found.", Headers({'header': ['value']}),
                     'GET', 'http://myurl.com')

        self.assertEqual(e.code, 404)
        self.assertEqual(e.body, "Not Found.")
        self.assertEqual(e.headers, Headers({'header': ['value']}))
        self.assertEqual(
            str(e),
            ("API Error code=404, body='Not Found.', "
             "headers=Headers({'header': ['value']}) (GET http://myurl.com)"))

    def test_api_error_with_Nones(self):
        """
        An APIError will be instantiated with an HTTP Code, an HTTP response
        body, and HTTP headers, and will expose these in public attributes and
        have a reasonable string representation even if the body, headers,
        method, and url are not provided.
        """
        e = APIError(404, None)

        self.assertEqual(e.code, 404)
        self.assertEqual(e.body, None)
        self.assertEqual(e.headers, None)
        self.assertEqual(
            str(e),
            "API Error code=404, body=None, headers=None (no_method no_url)"
        )

    def test_check_success(self):
        """
        check_success will return the response if the response.code is in
        success_codes.
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
        response.headers = Headers({})
        self.treq.content.return_value = succeed('Not Found.')

        d = check_success(response, [200, 201])
        f = self.failureResultOf(d)

        self.assertTrue(f.check(APIError))
        self.assertEqual(f.value.code, 404)
        self.assertEqual(f.value.body, 'Not Found.')
        self.assertEqual(f.value.headers, Headers({}))

    def test_headers_content_type(self):
        """
        headers will use a json content-type.
        """
        self.assertEqual(
            headers('any')['content-type'], ['application/json'])

    def test_headers_accept(self):
        """
        headers will use a json accept header.
        """
        self.assertEqual(
            headers('any')['accept'], ['application/json'])

    def test_headers_sets_auth_token(self):
        """
        headers will set the X-Auth-Token header based on it's auth_token
        argument.
        """
        self.assertEqual(
            headers('my-auth-token')['x-auth-token'], ['my-auth-token'])

    def test_headers_can_be_http_headers(self):
        """
        headers will produce a result that can be passed to
        twisted.web.http_headers.Headers.
        """
        self.assertIsInstance(Headers(headers('my-auth-token')), Headers)

    def test_headers_optional_auth_token(self):
        """
        headers will produce a dictionary without the x-auth-token header if no
        auth token is given.
        """
        self.assertNotIn('x-auth-token', headers())

    def test_connection_error(self):
        """
        A :class:`RequestError` instantiated with a netloc and a wrapped
        failure expose both attributes and have a valid repr and str.
        """
        failure = Failure(Exception())
        e = RequestError(failure, "xkcd.com", 'stuff')

        self.assertEqual(e.reason, failure)
        self.assertEqual(e.url, "xkcd.com")
        self.assertEqual(
            repr(e),
            "RequestError[xkcd.com, {0!r}, data=stuff]".format(Exception()))
        self.assertEqual(
            str(e),
            "RequestError[xkcd.com, {}, data=stuff]".format(str(failure)))

    def test_raise_error_on_code_matches_code(self):
        """
        ``raise_error_on_code`` expects an APIError, and raises a particular
        error given a specific code.  Otherwise, it just wraps it in a
        :class:`RequestError`
        """
        failure = Failure(APIError(404, '', {}))
        self.assertRaises(DummyException, raise_error_on_code,
                          failure, 404, DummyException(), 'url')

    def test_raise_error_on_code_does_not_match_code(self):
        """
        ``raise_error_on_code`` expects an APIError, and raises a particular
        error given a specific code.  Otherwise, it just wraps it in a
        :class:`RequestError`
        """
        failure = Failure(APIError(404, '', {}))
        self.assertRaises(RequestError, raise_error_on_code,
                          failure, 500, DummyException(), 'url')

    def test_wrap_request_error_raises_RequestError(self):
        """
        ``wrap_request_error`` raises a :class:`RequestError` of the
        failure that gets passed in
        """
        failure = Failure(Exception())
        self.assertRaises(RequestError, wrap_request_error,
                          failure, 'url')

    def test_try_json_with_keys_success(self):
        """
        ``try_json_with_keys`` will attempt to load some JSON, and pull
        the value at the given key set out.
        """
        json_blob = {'this': {'is': {'a': {'deeply': {'nested': 'dict'}}}}}
        message = try_json_with_keys(json.dumps(json_blob),
                                     ('this', 'is', 'a', 'deeply', 'nested'))
        self.assertEqual(message, 'dict')

    def test_try_json_with_keys_invalid_json(self):
        """
        ``try_json_with_keys``, if given invalid JSON, will return None as a
        message
        """
        self.assertIsNone(try_json_with_keys('s', ('s',)))

    def test_try_json_with_keys_no_such_key(self):
        """
        ``try_json_with_keys``, if given valid JSON, but keys that are not
        present in the loaded JSON, will return None as a message
        """
        self.assertIsNone(try_json_with_keys(json.dumps([1, 2, 3]), ('a',)))
        self.assertIsNone(
            try_json_with_keys(json.dumps({'a': [1, 2, 3]}), ('a', 4)))


class UpstreamErrorTests(SynchronousTestCase):
    """
    Tests for `UpstreamError`
    """

    def test_apierror_nova(self):
        """
        Wraps APIError from nova and parses error body accordingly
        """
        body = json.dumps({"computeFault": {"message": "b"}})
        apie = APIError(404, body, {})
        err = UpstreamError(Failure(apie), 'nova', 'add', 'xkcd.com')
        self.assertEqual(str(err), 'nova error: 404 - b (add)')
        self.assertEqual(err.details, {
            'system': 'nova', 'operation': 'add', 'url': 'xkcd.com',
            'message': 'b', 'code': 404, 'body': body, 'headers': {}})

    def test_apierror_clb(self):
        """
        Wraps APIError from clb and parses error body accordingly
        """
        body = json.dumps({"message": "b"})
        apie = APIError(403, body, {'h1': 2})
        err = UpstreamError(Failure(apie), 'clb', 'remove', 'xkcd.com')
        self.assertEqual(str(err), 'clb error: 403 - b (remove)')
        self.assertEqual(err.details, {
            'system': 'clb', 'operation': 'remove', 'url': 'xkcd.com',
            'message': 'b', 'code': 403, 'body': body, 'headers': {'h1': 2}})

    def test_apierror_identity(self):
        """
        Wraps APIError from identity and parses error body accordingly
        """
        body = json.dumps({"identityFault": {"message": "ba"}})
        apie = APIError(410, body, {})
        err = UpstreamError(Failure(apie), 'identity', 'stuff', 'xkcd.com')
        self.assertEqual(str(err), 'identity error: 410 - ba (stuff)')
        self.assertEqual(err.details, {
            'system': 'identity', 'operation': 'stuff', 'url': 'xkcd.com',
            'message': 'ba', 'code': 410, 'body': body, 'headers': {}})

    def test_apierror_unparsed(self):
        """
        Wraps APIError from identity and uses default string if unable to
        parse error body
        """
        body = json.dumps({"identityFault": {"m": "ba"}})
        apie = APIError(410, body, {})
        err = UpstreamError(Failure(apie), 'identity', 'stuff', 'xkcd.com')
        self.assertEqual(
            str(err),
            'identity error: 410 - Could not parse API error body (stuff)')
        self.assertEqual(err.details, {
            'system': 'identity', 'operation': 'stuff', 'url': 'xkcd.com',
            'message': 'Could not parse API error body', 'code': 410,
            'body': body, 'headers': {}})

    def test_non_apierror(self):
        """
        Wraps any other error and has message and details accordingly
        """
        err = UpstreamError(Failure(ValueError('heh')), 'identity',
                            'stuff', 'xkcd.com')
        self.assertEqual(str(err), 'identity error: heh (stuff)')
        self.assertEqual(err.details, {
            'system': 'identity', 'operation': 'stuff', 'url': 'xkcd.com'})


class CapabilityTests(SynchronousTestCase):
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


class TimestampTests(SynchronousTestCase):
    """
    Test timestamp utilities
    """
    @mock.patch('otter.util.timestamp.datetime', spec=['utcnow'])
    def test_now_returns_iso8601Z_timestamp_no_microseconds(self,
                                                            mock_datetime):
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
        ``datetime(MINYEAR, 1, 1, tzinfo=None)`` according to the docs.
        ``MIN`` returns this datetime in iso8601 zulu format.
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

    def test_epoch_to_utctimestr(self):
        """
        ``epoch_to_utctimestr`` generates correct ISO formatted string
        """
        self.assertEqual(
            timestamp.epoch_to_utctimestr(0), '1970-01-01T00:00:00Z')

    def test_timestamp_to_epoch(self):
        """
        ``timestamp_to_epoch`` returns an epoch as a float with microseconds.
        """
        self.assertEqual(
            timestamp.timestamp_to_epoch('1970-01-01T00:00:00Z'),
            0.0)
        self.assertEqual(
            timestamp.timestamp_to_epoch('2015-05-01T04:51:12.078580Z'),
            1430455872.078580)

    def test_datetime_to_epoch(self):
        """
        `datetime_to_epoch` returns EPOCH seconds for given datetime
        """
        self.assertEqual(
            timestamp.datetime_to_epoch(datetime(1970, 1, 1, 0, 0, 0)),
            0.0)
        self.assertEqual(
            timestamp.datetime_to_epoch(
                datetime(2015, 5, 1, 4, 51, 12, 78580)),
            1430455872.078580)


class ConfigTest(SynchronousTestCase):
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
        self.addCleanup(config.set_config_data, {})

    def test_top_level_value(self):
        """
        :func:`~config.config_value` returns the value stored at the top level key.
        """
        self.assertEqual(config.config_value('foo'), 'bar')

    def test_nested_value(self):
        """
        :func:`~config.config_value` returns the value stored at a . separated
        path.
        """
        self.assertEqual(config.config_value('baz.bax'), 'quux')

    def test_non_existent_value(self):
        """
        :func:`~config.config_value` will return :data`None` if the path does
        not exist in the nested dictionaries.
        """
        self.assertIdentical(config.config_value('baz.blah'), None)

    def test_nonexistent_value_with_shared_key_part_at_toplevel(self):
        """
        :func:`~config.config_value` will return :data`None` if the path does
        not exist in the nested dictionaries, even if some part of the path
        does. I.e. config_value is not allowed to ignore arbitrary path
        prefixes.
        """
        value = config.config_value('prefix.shouldnt.be.ignored.foo')
        self.assertIdentical(value, None)

    def test_update_config_existing(self):
        """
        :func:`~config.update_config_data` will update existing config
        and not remove others
        """
        config.update_config_data("baz.bax", "new")
        self.assertEqual(config.config_value("baz.bax"), "new")
        self.assertEqual(config.config_value("foo"), "bar")

    def test_update_config_new(self):
        """
        :func:`~config.update_config_data` will add new config and not remove
        others
        """
        config.update_config_data("baz.new", "wha")
        config.update_config_data("baz.some.other", "who")
        self.assertEqual(config.config_value("baz.new"), "wha")
        self.assertEqual(config.config_value("baz.some.other"), "who")
        self.assertEqual(config.config_value("baz.bax"), "quux")


class WithLockTests(SynchronousTestCase):
    """
    Tests for `with_lock`
    """

    def setUp(self):
        """
        Mock reactor, log and method
        """
        self.lock = LockMixin().mock_lock()
        self.acquire_d, self.release_d = Deferred(), Deferred()
        self.lock.acquire.side_effect = lambda: self.acquire_d
        self.lock.release.side_effect = lambda: self.release_d

        self.method_d = Deferred()
        self.method = mock.Mock(return_value=self.method_d)

        self.reactor = Clock()
        self.log = mock_log()
        self.log_fields = {'lock': self.lock, 'locked_func': self.method}

        # This is shared between multiple tests, and used in negative
        # assertions. Centralizing the definition means that if the message
        # changes the negative assertions will also be updated.
        self.too_long_message = "Lock held for more than 120 seconds!"

    def test_acquire_release(self):
        """
        Acquires, calls method, releases and returns method's result. Logs time taken
        """
        d = with_lock(self.reactor, self.lock, self.method, self.log)
        self.assertNoResult(d)
        self.log.msg.assert_called_once_with(
            'Starting lock acquisition', lock_status='Acquiring',
            **self.log_fields)
        self.reactor.advance(10)
        self.acquire_d.callback(None)
        self.log.msg.assert_called_with(
            'Lock acquisition in 10.0 seconds',
            lock_status='Acquired', acquire_time=10.0, **self.log_fields)
        self.method.assert_called_once_with()
        self.method_d.callback('result')

        self.log.msg.assert_called_with(
            'Starting lock release', lock_status='Releasing',
            **self.log_fields)
        self.reactor.advance(3)
        self.release_d.callback(None)
        self.log.msg.assert_called_with(
            'Lock release in 3.0 seconds',
            release_time=3.0, lock_status='Released', **self.log_fields)

        self.assertEqual(self.successResultOf(d), 'result')

        # And since the release successfully happened, the "held too long" log
        # message will _not_ be emitted
        self.reactor.advance(120)
        self.assertNotIn(
            self.too_long_message,
            (call[1][0] for call in self.log.msg.mock_calls))

    def test_acquire_release_no_log(self):
        """
        Acquires, calls method and releases even if log is None
        """
        d = with_lock(self.reactor, self.lock, self.method)
        self.assertNoResult(d)

        self.reactor.advance(10)
        self.acquire_d.callback(None)
        self.method.assert_called_once_with()
        self.method_d.callback('result')

        self.reactor.advance(3)
        self.release_d.callback(None)

        self.assertEqual(self.successResultOf(d), 'result')

    def test_acquire_failed(self):
        """
        If acquire fails, method and release is not called. Acquisition failed is logged
        """
        d = with_lock(self.reactor, self.lock, self.method, self.log)
        self.assertNoResult(d)
        self.log.msg.assert_called_once_with(
            'Starting lock acquisition', lock_status='Acquiring',
            **self.log_fields)

        self.reactor.advance(10)
        self.acquire_d.errback(ValueError(None))
        self.log.msg.assert_called_with(
            'Lock acquisition failed in 10.0 seconds', lock_status='Failed',
            **self.log_fields)
        self.assertFalse(self.method.called)
        self.failureResultOf(d, ValueError)

    def test_method_failure(self):
        """
        If method fails, lock is released and failure is propogated
        Acquisition and release is logged with time taken
        """
        self.method.return_value = fail(ValueError('a'))

        d = with_lock(self.reactor, self.lock, self.method, self.log)
        self.assertNoResult(d)
        self.log.msg.assert_called_once_with(
            'Starting lock acquisition', lock_status='Acquiring',
            **self.log_fields)

        self.reactor.advance(10)
        self.acquire_d.callback(None)
        self.assertEqual(
            self.log.msg.mock_calls[-2:],
            [mock.call('Lock acquisition in 10.0 seconds',
                       acquire_time=10.0, lock_status='Acquired',
                       **self.log_fields),
             mock.call('Starting lock release', lock_status='Releasing',
                       **self.log_fields)])
        self.method.assert_called_once_with()

        self.reactor.advance(3)
        self.release_d.callback(None)
        self.log.msg.assert_called_with('Lock release in 3.0 seconds',
                                        release_time=3.0,
                                        lock_status='Released',
                                        **self.log_fields)

        self.failureResultOf(d, ValueError)

    def test_acquire_timeout(self):
        """
        acquire is timed out if it does not succeed in a given time
        """
        d = with_lock(self.reactor, self.lock, self.method, self.log,
                      acquire_timeout=9)
        self.assertNoResult(d)
        self.log.msg.assert_called_once_with(
            'Starting lock acquisition', lock_status='Acquiring',
            **self.log_fields)

        self.reactor.advance(10)
        f = self.failureResultOf(d, TimedOutError)
        self.assertEqual(f.value.message,
                         'Lock acquisition timed out after 9 seconds.')
        self.log.msg.assert_called_with(
            'Lock acquisition failed in 10.0 seconds', lock_status='Failed',
            **self.log_fields)

        self.assertFalse(self.method.called)
        self.assertFalse(self.lock.release.called)

    def test_release_timeout(self):
        """
        release is timed out if it does not succeed in a given time
        """
        d = with_lock(self.reactor, self.lock, self.method, self.log,
                      release_timeout=9)
        self.acquire_d.callback(None)

        self.method.assert_called_once_with()
        self.method_d.callback('result')
        self.lock.release.assert_called_once_with()

        self.reactor.advance(10)
        f = self.failureResultOf(d, TimedOutError)
        self.assertEqual(f.value.message,
                         'Lock release timed out after 9 seconds.')

    def test_held_too_long(self):
        """When the lock is held for some time, a log message is emitted."""
        d = with_lock(self.reactor, self.lock, self.method, self.log)
        self.assertNoResult(d)
        self.acquire_d.callback(None)
        self.method.assert_called_once_with()
        self.reactor.advance(120)
        self.log.msg.assert_called_with(
            self.too_long_message,
            isError=True, lock_status='Acquired', **self.log_fields)


class DelayTests(SynchronousTestCase):
    """
    Tests for `delay`
    """

    def setUp(self):
        """
        Sample clock
        """
        self.clock = Clock()

    def test_delays(self):
        """
        Delays the result
        """
        d = delay(2, self.clock, 5)
        self.assertNoResult(d)
        self.clock.advance(5)
        self.assertEqual(self.successResultOf(d), 2)


class IsBoundWithTests(SynchronousTestCase):
    """
    Tests for :class:`otter.test.utils.IsBoundWith` class
    """

    def setUp(self):
        """
        Sample object
        """
        self.bound = IsBoundWith(a=10, b=20)

    def test_match_not_boundlog(self):
        """
        Does not match non `BoundLog`
        """
        m = self.bound.match('junk')
        self.assertEqual(m.describe(), 'log is not a BoundLog')

    def test_match_kwargs(self):
        """
        Returns None on matching kwargs
        """
        log = BoundLog(lambda: None, lambda: None).bind(a=10, b=20)
        self.assertIsNone(self.bound.match(log))

    def test_not_match_kwargs(self):
        """
        Returns mismatch on non-matching kwargs
        """
        log = BoundLog(lambda: None, lambda: None).bind(a=10, b=2)
        self.assertEqual(
            self.bound.match(log).describe(),
            'Expected kwargs {} but got {} instead'.format(dict(a=10, b=20), dict(a=10, b=2)))

    def test_nested_match(self):
        """
        works with Nested BoundLog
        """
        log = BoundLog(lambda: None, lambda: None).bind(a=10, b=20).bind(c=3)
        self.assertIsNone(IsBoundWith(a=10, b=20, c=3).match(log))

    def test_kwargs_order(self):
        """
        kwargs bound in order, i.e. next bound overriding previous bound should
        retain the value
        """
        log = BoundLog(lambda: None, lambda: None).bind(a=10, b=20).bind(a=3)
        self.assertIsNone(IsBoundWith(a=3, b=20).match(log))

    def test_str(self):
        """
        str(matcher) returns something useful
        """
        self.assertEqual(str(self.bound), 'IsBoundWith {}'.format(dict(a=10, b=20)))


class MatchesTests(SynchronousTestCase):
    """
    Tests for :class:`otter.test.utils.matches` class
    """

    def setUp(self):
        """
        Sample matches object
        """
        self.matcher = mock.MagicMock(spec=['match', '__str__'])
        self.matches = matches(self.matcher)

    def test_eq(self):
        """
        matches == another if matcher.match returns None
        """
        self.matcher.match.return_value = None
        self.assertEqual(self.matches, 2)
        self.matcher.match.assert_called_with(2)

    def test_not_eq(self):
        """
        matches != another if matcher.match does not return None
        """
        self.matcher.match.return_value = 'not none'
        self.assertNotEqual(self.matches, 2)
        self.matcher.match.assert_called_with(2)

    def test_repr(self):
        """
        repr(matches) returns matcher's representation
        """
        self.matcher.__str__.return_value = 'mystr'
        self.assertEqual(repr(self.matches), 'matches(mystr)')

    def test_repr_mismatch(self):
        """
        repr(matches) returns mismatch description also if match fails
        """
        self.matcher.__str__.return_value = 'ms'
        self.matcher.match.return_value = mock.Mock(describe=lambda: 'not none')
        self.matches == 'else'
        self.assertEqual(repr(self.matches), 'matches(ms): <mismatch: not none>')


class RetryOnUnauthTests(SynchronousTestCase):
    """
    Tests for :func:`otter.util.http.retry_on_unauth`
    """

    def setUp(self):
        """
        Sample auth function
        """

        def _auth():
            raise KeyError('e')

        self.auth = _auth

    def test_success(self):
        """
        `func` value is returned if it succeeds
        """
        d = retry_on_unauth(lambda: succeed('a'), self.auth)
        self.assertEqual(self.successResultOf(d), 'a')

    def test_non_upstream(self):
        """
        Any error other than UpstreamError is returned
        """
        d = retry_on_unauth(lambda: fail(ValueError('a')), self.auth)
        self.failureResultOf(d, ValueError)

    def test_non_apierror(self):
        """
        Any error other than APIError in UpstreamError is propogated
        """
        d = retry_on_unauth(
            lambda: fail(UpstreamError(Failure(ValueError('a')), 'identity', 'o')),
            self.auth)
        f = self.failureResultOf(d, UpstreamError)
        f.value.reason.trap(ValueError)

    def test_auth_error(self):
        """
        Calls auth() followed by func() again if initial func() returns 401
        """
        auth = mock.Mock(spec=[], return_value=succeed('a'))
        func = mock.Mock(side_effect=[
            fail(UpstreamError(Failure(APIError(401, '401')), 'identity', 'o')),
            succeed('r')])
        d = retry_on_unauth(func, auth)
        self.assertEqual(self.successResultOf(d), 'r')
        auth.assert_called_once_with()

    def test_500_error(self):
        """
        Any error other than 401 is propogated
        """
        d = retry_on_unauth(
            lambda: fail(UpstreamError(Failure(APIError(500, 'a')), 'identity', 'o')),
            self.auth)
        f = self.failureResultOf(d, UpstreamError)
        f.value.reason.trap(APIError)
        self.assertEqual(f.value.reason.value.code, 500)

    def test_auth_error_propogates(self):
        """
        `auth()` errors are propogated
        """
        auth = mock.Mock(spec=[], return_value=fail(ValueError('a')))
        func = mock.Mock(side_effect=[
            fail(UpstreamError(Failure(APIError(401, '401')), 'identity', 'o')),
            succeed('r')])
        d = retry_on_unauth(func, auth)
        self.failureResultOf(d, ValueError)
        auth.assert_called_once_with()
