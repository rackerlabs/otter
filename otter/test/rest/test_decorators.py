"""
Unit tests for the fault system
"""

from cStringIO import StringIO
import json
import mock

from jsonschema import ValidationError

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from otter.rest.decorators import (
    fails_with, select_dict, succeeds_with, validate_body, InvalidJsonError)
from otter.test.utils import DeferredTestMixin


class BlahError(Exception):
    """Null"""
    pass


class DetailsError(Exception):
    """Null"""
    details = 'this is a detail'


class FaultTestCase(DeferredTestMixin, TestCase):
    """Test case for the fault system"""
    def setUp(self):
        """ Basic Setup and patch the log """
        self.mockRequest = mock.MagicMock()
        self.mockRequest.code = None

        self.mockLog = mock.MagicMock()

        def mockResponseCode(code):
            self.mockRequest.code = code
        self.mockRequest.setResponseCode.side_effect = mockResponseCode

    def test_success(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """
        @fails_with({})
        @succeeds_with(204)
        def doWork(request, log):
            """ Test Work """
            return defer.succeed('hello')

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)
        self.assertEqual('hello', r)

    def test_success_ordering(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """
        @succeeds_with(204)
        @fails_with({})
        def doWork(request, log):
            """ Test Work """
            return defer.succeed('hello')

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)
        self.assertEqual('hello', r)

    def test_simple_failure(self):
        """
        Test simple failure case
        :return nothing
        """
        @fails_with({BlahError: 404})
        @succeeds_with(204)
        def doWork(request, log):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

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
        @fails_with({DetailsError: 404})
        @succeeds_with(204)
        def doWork(request, log):
            return defer.fail(DetailsError('fail'))

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

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
        @succeeds_with(204)
        @fails_with({DetailsError: 404})
        def doWork(request, log):
            return defer.fail(DetailsError('fail'))

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(404)

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

        @fails_with(select_dict([BlahError], mapping))
        @succeeds_with(204)
        def doWork(request, log):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(400)

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

        @fails_with(select_dict([KeyError], mapping))
        @succeeds_with(204)
        def doWork(request, log):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest, self.mockLog)
        r = self.assert_deferred_succeeded(d)
        self.mockRequest.setResponseCode.assert_called_once_with(500)

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "An Internal Error was encountered",
            "code": 500,
            "type": "InternalError",
            "details": ""
        })
        self.flushLoggedErrors(BlahError)


class ValidateBodyTestCase(DeferredTestMixin, TestCase):
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
            'otter.rest.decorators.jsonschema.validate')
        self.mock_validate = self.validate_patch.start()

    def tearDown(self):
        """
        Unpatch jsonschema
        """
        self.validate_patch.stop()

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

        @validate_body(schema)
        def handle_body(request, *args, **kwargs):
            return defer.succeed((args, kwargs))

        args = (1, 2, 3)
        kwargs = {'one': 'two'}

        d = handle_body(self.request, *args, **kwargs)
        result = self.assert_deferred_succeeded(d)

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

        @validate_body({})
        def handle_body(request, *args, **kwargs):
            return defer.succeed((args, kwargs))

        self.assert_deferred_failed(handle_body(self.request), InvalidJsonError)

    def test_validation_error(self):
        """
        If the request fails to validate, the decorator returns a
        ValidationError failure
        """
        def fail_to_validate(*args, **kwargs):
            raise ValidationError("Failure!")

        self.request.content.write('{}')
        self.mock_validate.side_effect = fail_to_validate

        @validate_body({})
        def handle_body(request, *args, **kwargs):
            return defer.succeed((args, kwargs))

        self.assert_deferred_failed(handle_body(self.request), ValidationError)
