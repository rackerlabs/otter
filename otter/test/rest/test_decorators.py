"""
Unit tests for the fault system
"""

from cStringIO import StringIO
import json
import mock

from jsonschema import ValidationError

from twisted.trial.unittest import TestCase
from twisted.internet import defer
from twisted.python.failure import Failure

from otter.rest.decorators import (
    fails_with, select_dict, succeeds_with, validate_body, InvalidJsonError,
    with_transaction_id, log_arguments, paginatable, InvalidQueryArgument)
from otter.util.config import set_config_data
from otter.test.utils import patch


class BlahError(Exception):
    """Null"""
    pass


class DetailsError(Exception):
    """Null"""
    details = 'this is a detail'


class TransactionIdTestCase(TestCase):
    """Test case for the transaction ID"""
    def setUp(self):
        """ Basic Setup and patch the log """
        self.mockRequest = mock.MagicMock()
        self.mockRequest.code = 200
        self.mockRequest.uri = '/'
        self.mockRequest.clientproto = 'HTTP/1.1'
        self.mockRequest.method = 'PROPFIND'
        values = {'referer': 'referrer(sic)',
                  'user-agent': 'Mosaic/1.0'}

        def header_side_effect(arg):
            return values[arg]

        self.mockRequest.getHeader.side_effect = header_side_effect

        def mockResponseCode(code):
            self.mockRequest.code = code
        self.mockRequest.setResponseCode.side_effect = mockResponseCode

        self.mock_log = patch(self, 'otter.rest.decorators.log')

        self.hashkey_patch = mock.patch(
            'otter.rest.decorators.generate_transaction_id')
        self.mock_key = self.hashkey_patch.start()
        self.mock_key.return_value = '12345678'
        self.addCleanup(self.hashkey_patch.stop)

    def test_success(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """

        class FakeApp(object):
            @with_transaction_id()
            def doWork(self, request, log):
                """ Test Work """
                return defer.succeed('hello')

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)

        self.mock_log.bind.assert_called_once_with(
            system='otter.test.rest.test_decorators.doWork',
            transaction_id='12345678')
        self.assertEqual(self.mock_log.bind().bind.call_args_list[0],
                         mock.call(useragent='Mosaic/1.0',
                                   clientproto='HTTP/1.1',
                                   referer='referrer(sic)',
                                   uri='/',
                                   method='PROPFIND'))
        self.mockRequest.setHeader.called_once_with('X-Response-Id', '12345678')
        self.assertEqual('hello', r)

    def test_log_bound(self):
        """
        the returned log is bound with kwargs passed
        """
        class FakeApp(object):
            @with_transaction_id()
            def doWork(self, request, log, arg1, arg2):
                """ Test Work """
                return defer.succeed('hello')

        d = FakeApp().doWork(self.mockRequest, arg1='a1', arg2='a2')
        self.assertEqual('hello', self.successResultOf(d))
        self.mock_log.bind().bind.assert_called_with(arg1='a1', arg2='a2')


class FaultTestCase(TestCase):
    """Test case for the fault system"""
    def setUp(self):
        """ Basic Setup and patch the log """
        self.mockRequest = mock.MagicMock()
        self.mockRequest.code = 200
        self.mockRequest.uri = '/'

        self.mockLog = mock.MagicMock()

        def mockResponseCode(code):
            self.mockRequest.code = code
        self.mockRequest.setResponseCode.side_effect = mockResponseCode

    def test_success(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """
        class FakeApp(object):
            log = self.mockLog

            @fails_with({})
            @succeeds_with(204)
            def doWork(self, request):
                """ Test Work """
                return defer.succeed('hello')

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)

        self.mockLog.bind.assert_called_once_with(code=204, uri='/')
        self.mockLog.bind().msg.assert_called_once_with('Request succeeded')

        self.assertEqual('hello', r)

    def test_success_ordering(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """
        class FakeApp(object):
            log = self.mockLog

            @succeeds_with(204)
            @fails_with({})
            def doWork(self, request):
                """ Test Work """
                return defer.succeed('hello')

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)
        self.mockLog.bind.assert_called_once_with(code=204, uri='/')
        self.mockLog.bind().msg.assert_called_once_with('Request succeeded')

        self.assertEqual('hello', r)

    def test_simple_failure(self):
        """
        Test simple failure case
        :return nothing
        """
        class FakeApp(object):
            log = self.mockLog

            @fails_with({BlahError: 404})
            @succeeds_with(204)
            def doWork(self, request):
                return defer.fail(BlahError('fail'))

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

        self.mockLog.bind.assert_called_once_with(code=404, uri='/',
                                                  details='', message='fail',
                                                  type='BlahError')
        self.mockLog.bind().msg.assert_called_once_with('fail')

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "fail",
            "code": 404,
            "type": "BlahError",
            "details": ""
        })
        self.flushLoggedErrors(BlahError)

    def test_details_failure(self):
        """
        Test that detailed failures work
        :return nothing
        """
        class FakeApp(object):
            log = self.mockLog

            @fails_with({DetailsError: 404})
            @succeeds_with(204)
            def doWork(self, request):
                return defer.fail(DetailsError('fail'))

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

        self.mockLog.bind.assert_called_once_with(code=404, uri='/',
                                                  details='this is a detail',
                                                  message='fail',
                                                  type='DetailsError')
        self.mockLog.bind().msg.assert_called_once_with('fail')

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "fail",
            "code": 404,
            "type": "DetailsError",
            "details": "this is a detail"
        })
        self.flushLoggedErrors(DetailsError)

    def test_details_failure_ordering(self):
        """
        Test that detailed failures work
        :return nothing
        """
        class FakeApp(object):
            log = self.mockLog

            @succeeds_with(204)
            @fails_with({DetailsError: 404})
            def doWork(self, request):
                return defer.fail(DetailsError('fail'))

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

        # Not testing the logging here; if you do it out of order, it still
        # works but the logging is a bit spammy

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "fail",
            "code": 404,
            "type": "DetailsError",
            "details": "this is a detail"
        })
        self.flushLoggedErrors(DetailsError)

    def test_select_dict(self):
        """
        Tests that the select_dict function works
        :return nothing
        """
        mapping = {KeyError: 404, BlahError: 400}
        res = select_dict([KeyError], mapping)
        self.assertEqual({KeyError: 404}, res)

    def test_specified_failure(self):
        """
        Tests that you can select a specific error from the schema
        and fail on it.
        :return nothing
        """
        mapping = {KeyError: 404, BlahError: 400}

        class FakeApp(object):
            log = self.mockLog

            @fails_with(select_dict([BlahError], mapping))
            @succeeds_with(204)
            def doWork(self, request):
                return defer.fail(BlahError('fail'))

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(400)

        self.mockLog.bind.assert_called_once_with(code=400, uri='/',
                                                  details='', message='fail',
                                                  type='BlahError')
        self.mockLog.bind().msg.assert_called_once_with('fail')

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "fail",
            "code": 400,
            "type": "BlahError",
            "details": ""
        })
        self.flushLoggedErrors(BlahError)

    def test_unspecified_failure(self):
        """
        Tests that errors that were not expected will 500
        :return nothing
        """
        mapping = {KeyError: 404, BlahError: 400}
        blah = BlahError('fail')

        class FakeApp(object):
            log = self.mockLog

            @fails_with(select_dict([KeyError], mapping))
            @succeeds_with(204)
            def doWork(self, request):
                return defer.fail(blah)

        d = FakeApp().doWork(self.mockRequest)
        r = self.successResultOf(d)
        self.mockRequest.setResponseCode.assert_called_once_with(500)

        class _CmpFailure(object):
            def __init__(self, exception):
                self._exception = exception

            def __eq__(self, other):
                return isinstance(other, Failure) and other.value == self._exception

        self.mockLog.bind.assert_called_once_with(code=500, uri='/')
        self.mockLog.bind().err.assert_called_once_with(
            _CmpFailure(blah),
            'Unhandled Error handling request'
        )

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "An Internal Error was encountered",
            "code": 500,
            "type": "InternalError",
            "details": ""
        })
        self.flushLoggedErrors(BlahError)


class ValidateBodyTestCase(TestCase):
    """
    Tests for the `validate_body` decorator
    """

    def setUp(self):
        """
        Set up a mock requst object that can be read, also patch jsonschema
        """
        self.request_content = StringIO()
        self.request = mock.MagicMock(spec=["content"],
                                      content=self.request_content)

        self.validate_patch = mock.patch(
            'otter.rest.decorators.validate')
        self.mock_validate = self.validate_patch.start()
        self.addCleanup(self.validate_patch.stop)

    def test_success_case(self):
        """
        The decorator should seek to the request content's beginning, attempt
        to load it via JSON, validates, and then passes the decorated function
        the json data as the keyword "data"
        """
        expected_value = {'hey': 'there'}
        schema = {'some': 'schema'}

        json.dump(expected_value, self.request_content)
        self.request_content.seek(4)  # do not start at the begining
        self.mock_validate.return_value = None  # validation should pass

        class FakeApp(object):
            @validate_body(schema)
            def handle_body(self, request, *args, **kwargs):
                return defer.succeed((args, kwargs))

        args = (1, 2, 3)
        kwargs = {'one': 'two'}

        d = FakeApp().handle_body(self.request, *args, **kwargs)
        result = self.successResultOf(d)

        # assert that it was validated
        self.mock_validate.assert_called_once_with(expected_value, schema)

        # assert that the json was parsed and passed back in the 'data' keyword
        expected_kwargs = dict(kwargs)
        expected_kwargs['data'] = expected_value
        self.assertEqual(result, (args, expected_kwargs))

    def test_not_json_error(self):
        """
        If the request content isn't actually json, the decorator returns a
        InvalidJsonError failure.
        """
        self.request_content.write('not actually json')
        self.mock_validate.return_value = None  # would otherwise pass

        class FakeApp(object):
            @validate_body({})
            def handle_body(self, request, *args, **kwargs):
                return defer.succeed((args, kwargs))

        self.failureResultOf(FakeApp().handle_body(self.request), InvalidJsonError)

    def test_validation_error(self):
        """
        If the request fails to validate, the decorator returns a
        ValidationError failure
        """
        def fail_to_validate(*args, **kwargs):
            raise ValidationError("Failure!")

        self.request.content.write('{}')
        self.mock_validate.side_effect = fail_to_validate

        class FakeApp(object):
            @validate_body({})
            def handle_body(self, request, *args, **kwargs):
                return defer.succeed((args, kwargs))

        self.failureResultOf(FakeApp().handle_body(self.request), ValidationError)


class LogArgumentsTestCase(TestCase):
    """
    Tests for the `log_arguments` decorator
    """

    def setUp(self):
        """
        SetUp a mock request and log for testing `log_arguments`.
        """
        self.mockRequest = mock.MagicMock()
        self.mockRequest.code = 200
        self.mockRequest.uri = '/'

        self.mockLog = mock.MagicMock()

    def test_no_arguments_logged(self):
        """
        Nothing is bound to the log on routes with no extra arguments.
        """
        class FakeApp(object):
            log = self.mockLog

            @log_arguments
            def doWork(self, request):
                return defer.succeed('')

        d = FakeApp().doWork(self.mockRequest)
        self.successResultOf(d)

        self.mockLog.bind.assert_called_once_with()

    def test_multiple_arguments_logged(self):
        """
        Extra kwargs are bound to the log
        """
        class FakeApp(object):
            log = self.mockLog

            @log_arguments
            def doWork(self, request, extra_arg1, **kwargs):
                return defer.succeed('')

        kwargs = {'truth': 42}

        d = FakeApp().doWork(self.mockRequest, 'ignored', **kwargs)
        self.successResultOf(d)

        self.mockLog.bind.assert_called_once_with(**kwargs)


class PaginatableTestCase(TestCase):
    """
    Tests for the `paginatable` decorator
    """
    def setUp(self):
        """
        SetUp a mock request with query args for testing `paginatable`.
        """
        self.mockRequest = mock.MagicMock()
        self.mockRequest.args = {}

        class FakeApp(object):
            @paginatable
            def paginate_me(self, request, paginate):
                return defer.succeed(paginate)

        self.app = FakeApp()

        set_config_data({'limit': {'pagination': 10}})
        self.addCleanup(lambda: set_config_data(None))

    def test_no_query_arguments(self):
        """
        When there are no query arguments in the request, the paginate
        dictionary contains only the default limit value.
        """
        d = self.app.paginate_me(self.mockRequest)
        self.assertEqual(self.successResultOf(d), {'limit': 10})

    def test_integer_limit_value(self):
        """
        Decorator turns the limit value into an integer
        """
        self.mockRequest.args['limit'] = ['5']
        d = self.app.paginate_me(self.mockRequest)
        self.assertEqual(self.successResultOf(d), {'limit': 5})

    def test_invalid_limit_value(self):
        """
        Decorator raises InvalidQueryArgument if the limit argument cannot be
        coerced into an integer.
        """
        self.mockRequest.args['limit'] = ['X']
        d = self.app.paginate_me(self.mockRequest)
        self.failureResultOf(d, InvalidQueryArgument)

    def test_invalid_query_keys(self):
        """
        Decorator ignores invalid query keys (only propagates the 'limit' and
        'marker' keys)
        """
        self.mockRequest.args['magnitude'] = ['pop', 'pop']
        d = self.app.paginate_me(self.mockRequest)
        self.assertEqual(self.successResultOf(d), {'limit': 10})

    def test_multiple_query_values(self):
        """
        Decorator picks only the first value matching valid query keys
        """
        self.mockRequest.args['marker'] = ['1234', '5678']
        d = self.app.paginate_me(self.mockRequest)
        self.assertEqual(self.successResultOf(d),
                         {'marker': '1234', 'limit': 10})
