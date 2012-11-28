"""
Unit tests for the fault system
"""

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from otter.test.utils import DeferredTestMixin
from mock import MagicMock

import json

from otter.util.fault import fails_with, select_dict, succeeds_with


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
        self.mockRequest = MagicMock()
        self.mockRequest.code = None

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
        def doWork(request):
            """ Test Work """
            return defer.succeed('hello')

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)
        self.assertEqual('hello', r)

    def test_success_ordering(self):
        """
        Test to make sure it works in the success case
        :return nothing
        """
        @succeeds_with(204)
        @fails_with({})
        def doWork(request):
            """ Test Work """
            return defer.succeed('hello')

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
        self.mockRequest.setResponseCode.assert_called_once_with(204)
        self.assertEqual('hello', r)

    def test_simple_failure(self):
        """
        Test simple failure case
        :return nothing
        """
        @fails_with({BlahError: 404})
        @succeeds_with(204)
        def doWork(request):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
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
        def doWork(request):
            return defer.fail(DetailsError('fail'))

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
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
        def doWork(request):
            return defer.fail(DetailsError('fail'))

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
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
        def doWork(request):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
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
        def doWork(request):
            return defer.fail(BlahError('fail'))

        d = doWork(self.mockRequest)
        r = self.assert_deferred_fired(d)
        self.mockRequest.setResponseCode.assert_called_once_with(500)

        faultDoc = json.loads(r)
        self.assertEqual(faultDoc, {
            "message": "An Internal Error was encountered",
            "code": 500,
            "type": "InternalError",
            "details": ""
        })
        self.flushLoggedErrors(BlahError)
