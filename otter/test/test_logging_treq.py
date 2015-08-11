"""
Tests for logging treq
"""
import mock

import treq

from twisted.internet.defer import Deferred, succeed
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from otter.util import logging_treq
from otter.util.deferredutils import TimedOutError
from otter.test.utils import CheckFailure, DummyException, mock_log, patch


class LoggingTreqTest(SynchronousTestCase):
    """
    Test to make sure all treq methods are supported and all requests are
    logged.
    """
    def setUp(self):
        """
        Set up some mocks.
        """
        self.log = mock_log()
        self.clock = Clock()

        configuration = {}

        for method in ('request', 'head', 'get', 'put', 'patch', 'post',
                       'delete'):
            configuration['{0}.__name__'.format(method)] = method
            configuration['{0}.return_value'.format(method)] = Deferred()

        self.treq = mock.MagicMock(spec=treq, **configuration)

        self.response = mock.MagicMock(code=204, headers={'1': '2'})

        patch(self, 'otter.util.logging_treq.treq', self.treq)
        patch(self, 'otter.util.logging_treq.uuid4',
              mock.MagicMock(spec=[], return_value='uuid'))
        self.url = 'myurl'

    def _assert_success_logging(self, method, status, request_time,
                                url_params=None, body=None):
        """
        msg expected to be made on a successful request are logged
        """
        response_kwargs = {
            'url': self.url,
            'status_code': status,
            'headers': {'1': '2'},
            'method': method,
            'treq_request_id': 'uuid',
            'url_params': url_params,
            'system': "treq.request",
            'request_time': request_time
        }
        if body is not None:
            response_kwargs['response_body'] = body

        self.assertEqual(self.log.msg.mock_calls, [
            mock.call(mock.ANY, url=self.url, system="treq.request",
                      method=method, treq_request_id='uuid',
                      url_params=url_params),
            mock.call(mock.ANY, **response_kwargs)
        ])

    def _assert_failure_logging(self, method, exception_type, request_time):
        """
        msg expected to be made on a failed request are logged
        """
        self.assertEqual(self.log.msg.mock_calls, [
            mock.call(mock.ANY, url=self.url, system="treq.request",
                      method=method, treq_request_id='uuid',
                      url_params=None),
            mock.call(
                mock.ANY, url=self.url, reason=CheckFailure(exception_type),
                system="treq.request", request_time=request_time,
                method=method, treq_request_id='uuid', url_params=None)
        ])

    def test_request(self):
        """
        On successful call to request, response is returned and request logged
        """
        d = logging_treq.request('patch', self.url, headers={}, data='',
                                 log=self.log, clock=self.clock)
        self.treq.request.assert_called_once_with(
            method='patch', url=self.url,
            headers={'x-otter-request-id': ['uuid']}, data='')
        self.assertNoResult(d)

        self.clock.advance(5)
        self.treq.request.return_value.callback(self.response)

        self.assertIs(self.successResultOf(d), self.response)
        self._assert_success_logging('patch', 204, 5)

    def test_url_params(self):
        """`params` is logged as `url_params`."""
        params = {'key': 'val'}
        d = logging_treq.request('get', self.url, data='',
                                 log=self.log, params=params, clock=self.clock)
        self.clock.advance(5)
        self.treq.request.return_value.callback(self.response)
        self.treq.request.assert_called_once_with(
            method='get', url=self.url,
            headers={'x-otter-request-id': ['uuid']}, data='', params=params)
        self.assertIs(self.successResultOf(d), self.response)
        self._assert_success_logging('get', 204, 5, url_params=params)

    def test_headers_are_preserved_except_request_id(self):
        """
        `headers` are passed through as is, with an `x-otter-request-id` added.
        If the header `x-otter-request-id` is supplied in the existing headers,
        it is replaced.
        """
        headers = {'header1': ['val1'], 'header2': ['val2'],
                   'x-otter-almost-it': ['unchanged'],
                   'x-otter-request-id': ['different-value']}
        new_headers = headers.copy()
        new_headers['x-otter-request-id'] = ['uuid']
        logging_treq.request('get', self.url, headers=headers, log=self.log,
                             clock=self.clock)
        self.treq.request.assert_called_once_with(
            method='get', url=self.url, headers=new_headers)

    def test_request_failure(self):
        """
        On failed call to request, failure is returned and request logged
        """
        d = logging_treq.request('patch', self.url, data='',
                                 log=self.log, clock=self.clock)
        self.treq.request.assert_called_once_with(
            method='patch', url=self.url,
            headers={'x-otter-request-id': ['uuid']}, data='')
        self.assertNoResult(d)

        self.clock.advance(5)
        self.treq.request.return_value.errback(Failure(DummyException('e')))

        self.failureResultOf(d, DummyException)
        self._assert_failure_logging('patch', DummyException, 5)

    def test_request_timeout(self):
        """
        A request times out after 45 seconds, and the failure is logged
        """
        d = logging_treq.request('patch', self.url, data='', headers=None,
                                 log=self.log, clock=self.clock)
        self.treq.request.assert_called_once_with(
            method='patch', url=self.url,
            headers={'x-otter-request-id': ['uuid']}, data='')
        self.assertNoResult(d)

        self.clock.advance(45)
        self.failureResultOf(d, TimedOutError)
        self._assert_failure_logging('patch', TimedOutError, 45)

    def test_request_with_response_logging(self):
        """
        On a successful request with response logging turned on, response is
        returned and request with body is logged.
        """
        self.treq.request.return_value.callback(self.response)
        self.treq.content.return_value = succeed("this is the body")

        ltreq = logging_treq.LoggingTreq(log_response=True)
        d = ltreq.request('patch', self.url, headers={}, data='',
                          log=self.log, clock=self.clock)
        self.assertIs(self.successResultOf(d), self.response)
        self._assert_success_logging('patch', 204, 0, body='this is the body')

    def _test_method_success(self, method):
        """
        On successful call to ``method``, response is returned and request
        logged.
        """
        request_function = getattr(logging_treq, method)
        d = request_function(url=self.url, headers={}, data='', log=self.log,
                             clock=self.clock)

        treq_function = getattr(self.treq, method)
        treq_function.assert_called_once_with(
            url=self.url, headers={'x-otter-request-id': ['uuid']}, data='')

        self.assertNoResult(d)

        self.clock.advance(5)
        treq_function.return_value.callback(self.response)

        self.assertIs(self.successResultOf(d), self.response)
        self._assert_success_logging(method, 204, 5)

    def _test_method_failure(self, method):
        """
        On failed call to ``method``, failure is returned and request logged
        """
        request_function = getattr(logging_treq, method)
        d = request_function(url=self.url, headers={}, data='', log=self.log,
                             clock=self.clock)

        treq_function = getattr(self.treq, method)
        treq_function.assert_called_once_with(
            url=self.url, headers={'x-otter-request-id': ['uuid']}, data='')
        self.assertNoResult(d)

        self.clock.advance(5)
        treq_function.return_value.errback(Failure(DummyException('e')))

        self.failureResultOf(d, DummyException)
        self._assert_failure_logging(method, DummyException, 5)

    def _test_method_timeout(self, method):
        """
        A request times out after 45 seconds, and the failure is logged
        """
        request_function = getattr(logging_treq, method)
        d = request_function(url=self.url, headers={}, data='', log=self.log,
                             clock=self.clock)

        treq_function = getattr(self.treq, method)
        treq_function.assert_called_once_with(
            url=self.url, headers={'x-otter-request-id': ['uuid']}, data='')
        self.assertNoResult(d)

        self.clock.advance(45)
        self.failureResultOf(d, TimedOutError)
        self._assert_failure_logging(method, TimedOutError, 45)

    def test_head(self):
        """
        On successful call to get, response is returned and request logged
        """
        self._test_method_success('head')

    def test_head_failure(self):
        """
        On failed call to head, failure is returned and request logged
        """
        self._test_method_failure('head')

    def test_head_timeout(self):
        """
        On timed out call to head, failure is returned and request logged
        """
        self._test_method_timeout('head')

    def test_get(self):
        """
        On successful call to get, response is returned and request logged
        """
        self._test_method_success('get')

    def test_get_failure(self):
        """
        On failed call to get, failure is returned and request logged
        """
        self._test_method_failure('get')

    def test_get_timeout(self):
        """
        On timed out call to get, failure is returned and request logged
        """
        self._test_method_timeout('get')

    def test_post(self):
        """
        On successful call to post, response is returned and request logged
        """
        self._test_method_success('post')

    def test_post_failure(self):
        """
        On failed call to post, failure is returned and request logged
        """
        self._test_method_failure('post')

    def test_post_timeout(self):
        """
        On timed out call to post, failure is returned and request logged
        """
        self._test_method_timeout('post')

    def test_put(self):
        """
        On successful call to put, response is returned and request logged
        """
        self._test_method_success('put')

    def test_put_failure(self):
        """
        On failed call to put, failure is returned and request logged
        """
        self._test_method_failure('put')

    def test_put_timeout(self):
        """
        On timed out call to put, failure is returned and request logged
        """
        self._test_method_timeout('put')

    def test_patch(self):
        """
        On successful call to patch, response is returned and request logged
        """
        self._test_method_success('patch')

    def test_patch_failure(self):
        """
        On failed call to patch, failure is returned and request logged
        """
        self._test_method_failure('patch')

    def test_patch_timeout(self):
        """
        On timed out call to patch, failure is returned and request logged
        """
        self._test_method_timeout('patch')

    def test_delete(self):
        """
        On successful call to delete, response is returned and request logged
        """
        self._test_method_success('delete')

    def test_delete_failure(self):
        """
        On failed call to delete, failure is returned and request logged
        """
        self._test_method_failure('delete')

    def test_delete_timeout(self):
        """
        On timed out call to delete, failure is returned and request logged
        """
        self._test_method_timeout('delete')

    def test_module_contents_mapped_to_treq_contents(self):
        """
        ``content``, ``json_content``, and ``text_content`` are just directly
        mapped to treq.  Not the patched treq, because the functions are
        already assigned at import time, and thus patching treq won't
        reassign these module attributes.
        """
        for name in ('content', 'json_content', 'text_content'):
            expected = getattr(treq, name)
            actual = getattr(logging_treq, name)
            self.assertIs(actual, expected,
                          "{0}.{1} ({2}) is not treq.{1} ({3})"
                          .format(logging_treq.__name__, name, actual,
                                  expected))

    def test_new_logging_treq_contents_mapped_to_treq_contents(self):
        """
        ``content``, ``json_content``, and ``text_content`` of a newly created
        LoggingTreq instance are just directly mapped to the patched treq
        functions..
        """
        ltreq_instance = logging_treq.LoggingTreq()
        for name in ('content', 'json_content', 'text_content'):
            expected = getattr(self.treq, name)
            actual = getattr(ltreq_instance, name)
            self.assertIs(actual, expected,
                          "{0}.{1} ({2}) is not treq.{1} ({3})"
                          .format(ltreq_instance.__name__, name, actual,
                                  expected))
