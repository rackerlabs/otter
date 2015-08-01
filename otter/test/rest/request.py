"""
Utilities for testing the REST API, including a way of mock requesting a
response from the rest resource.
"""

from collections import namedtuple
from urlparse import urlsplit

from klein.test.test_resource import requestMock

import mock

from twisted.internet import defer
from twisted.web import server, http
from twisted.web.resource import getChildForRequest
from twisted.web.server import Request
from twisted.web.http import parse_qs

from otter.models.interface import IAdmin, IScalingGroup, IScalingGroupCollection
from otter.rest.application import Otter
from otter.rest.admin import OtterAdmin
from otter.test.utils import iMock, patch
from otter.util.config import set_config_data


def _render(resource, request):
    result = resource.render(request)
    if isinstance(result, str):
        request.write(result)
        request.finish()
        return defer.succeed(None)
    elif result is server.NOT_DONE_YET:
        if request.finished:
            return defer.succeed(None)
        else:
            return request.notifyFinish()
    else:
        raise ValueError("Unexpected return value: %r" % (result,))


ResponseWrapper = namedtuple('ResponseWrapper', ['response', 'content', 'request'])


def request(root_resource, method, endpoint, headers=None, body=None):
    """
    Make a mock request to the REST interface

    :param method: http method
    :type method: ``str`` in (``GET``, ``POST``, ``PUT``, ``DELETE``)

    :param endpoint: Absolute path to the endpoint, minus the API version
    :type endpoint: ``str``

    :param headers: Any headers to include
    :type headers: ``dict`` of ``list``

    :param body: the body to include in the request
    :type body: ``str``
    """
    # handle query args, since requestMock does not (see
    # twisted.web.http.py:Request.requestReceived)
    with_query = endpoint.split(b'?', 1)
    if len(with_query) == 1:
        mock_request = requestMock(endpoint, method, headers=headers, body=body)
        mock_request.args = {}
    else:
        mock_request = requestMock(with_query[0], method, headers=headers,
                                   body=body)
        mock_request.args = parse_qs(with_query[1])

    # these are used when writing the response
    mock_request.code = 200
    mock_request.getClientIP = mock.MagicMock(spec=(), return_value='ip')
    mock_request.setHeader = mock.MagicMock(spec=())

    # twisted request has a responseHeaders (outgoing headers) and
    # requestHeaders (incoming headers, set by requestMock)
    mock_request.responseHeaders = http.Headers()

    # if setHeader has been called a with unicode value, twisted will raise a
    # TypeError after the request has been closed and it is attemptig to write
    # to the network.  So just fail here for testing purposes
    def _twisted_compat(name, value):
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("Can only pass-through bytes on Python 2")
        mock_request.responseHeaders.addRawHeader(name, value)

    mock_request.setHeader.side_effect = _twisted_compat

    def build_response(_):
        # build a response that offers some useful attributes of an IResponse
        status_code = 200
        if mock_request.setResponseCode.call_args is not None:
            # first non-keyword arg - getting it from call_args means the non
            # kwargs are the first argument, not the second
            status_code = mock_request.setResponseCode.call_args[0][0]

        # if the content-type has not been set, Twisted by default sets the
        # content-type to be whatever is in
        # twisted.web.server.Request.defaultContentType, so replicate that
        # functionality
        if not (mock_request.responseHeaders.hasHeader('Content-Type') or
                Request.defaultContentType is None):
            mock_request.responseHeaders.setRawHeaders(
                'Content-Type', [Request.defaultContentType])

        # Annoying implementation detail: if the status code is one of the
        # status codes that should not have a body, twisted replaces the
        # write method of the request with a function that does nothing, so
        # no response body can every be written.  This messes up the mock
        # request's write function (which just returns another mock).  So
        # in this case, just return the empty string.
        content = ''
        if status_code not in http.NO_BODY_CODES:
            content = mock_request.getWrittenData()

        response = mock.MagicMock(spec=['code', 'headers'],
                                  code=status_code,
                                  headers=mock_request.responseHeaders)
        return ResponseWrapper(response=response,
                               content=content,
                               request=mock_request)

    return _render(
        getChildForRequest(root_resource, mock_request),
        mock_request).addCallback(build_response)


def path_only(url):
    """
    Retrieves the path-only part of a URL

    :param url: the url to remove the host and scheme from
    :type url: ``str``
    """
    return urlsplit(url).path


class DummyException(Exception):
    """
    A dummy exception to be passed around as if it was a real one.

    This way we are certain to throw a completely unhandled exception
    """


class RequestTestMixin(object):
    """
    Mixin that has utilities for asserting something about the status code,
    getting header info, etc.
    """

    def assert_response(self, response_wrapper, expected_status, message=None):
        """
        Asserts that the response wrapper has the provided status code and
        that it has a response ID header and the correct content-type header.

        :param response_wrapper: the callbacked result from :func:`request`
        :type response_wrapper: :class:`ResponseWrapper`

        :param expected_status: what the response status code should be
        :type expected_status: ``int``

        :return: None
        """
        # If we're expecting a 405 or a 301, it never hits the decorator;
        # otherwise it needs to have sent a transaction ID, and its
        # content-type must be set to application/json
        #
        # There are probably other response codes we need to add here,
        # but I don't have a good idea for how best to discover them.
        #
        headers = response_wrapper.response.headers

        error_message = [
            "Got status {0} but expected {1}".format(
                response_wrapper.response.code, expected_status),
            "Request URI: {0}".format(response_wrapper.request.uri),
            "Response: {0}".format(response_wrapper.content)]
        if message:
            error_message.insert(0, message)

        self.assertEqual(response_wrapper.response.code, expected_status,
                         "\n".join(error_message))

        if expected_status not in [405, 301]:
            self.assertNotEqual(headers.getRawHeaders('X-Response-ID'), None)
            self.assertEqual(headers.getRawHeaders('Content-Type'),
                             ['application/json'])
        else:
            content_type = headers.getRawHeaders('Content-Type')[0]
            self.assertIn('text/html', content_type)

    def get_location_header(self, response_wrapper):
        """
        If a location header is expected, retrieves the location header from
        the response wrapper (also asserts that there is a location header and
        that the location should only have been set once)

        :param response_wrapper: the callbacked result from :func:`request`
        :type response_wrapper: :class:`ResponseWrapper`

        :return: the location header of the response wrapper
        :rtype: ``str``
        """
        locations = response_wrapper.response.headers.getRawHeaders('location')

        self.assertNotEqual(locations, None)
        self.assertEqual(len(locations), 1,
                         "Too many location headers: {0!r}".format(locations))
        return locations[0]

    def assert_status_code(self, expected_status, endpoint=None,
                           method="GET", body="", location=None,
                           root=None):
        """
        Asserts that the status code of a particular request with the given
        endpoint, request method, request body results in the provided status
        code.

        :param expected_status: what the response status code should be
        :type expected_status: ``int``

        :param endpoint: what the URI in the request should be
        :type endpoint: ``string``

        :param method: what method the request should use: "GET", "DELETE",
            "POST", or "PUT"
        :type method: ``string``

        :param body: what the request body should contain
        :type body: ``string``

        :param location: what the location header should contain
        :type location: ``string``

        :return: the response body as a string
        """
        response_wrapper = self.request(endpoint, method, body, root)

        self.assert_response(response_wrapper, expected_status)
        if location is not None:
            self.assertEqual(self.get_location_header(response_wrapper),
                             location)
        return response_wrapper.content

    def request(self, endpoint=None, method="GET", body="", root=None):
        """
        Make a pretend request to otter

        :param endpoint: what the URI in the request should be
        :type endpoint: ``string``

        :param method: what method the request should use: "GET", "DELETE",
            "POST", or "PUT"
        :type method: ``string``

        :param body: what the request body should contain
        :type body: ``string``

        :return: :class:`ResponseWrapper`
        """
        if root is None:
            if not hasattr(self, 'root'):
                root = Otter(iMock(IScalingGroupCollection)).app.resource()
            else:
                root = self.root

        return self.successResultOf(
            request(root, method, endpoint or self.endpoint, body=body))


class RestAPITestMixin(RequestTestMixin):
    """
    Setup and teardown for tests for the REST API endpoints
    """

    def setUp(self):
        """
        Mock the interface

        :return: None
        """
        self.mock_store = iMock(IScalingGroupCollection)
        self.mock_group = iMock(IScalingGroup)
        self.mock_store.get_scaling_group.return_value = self.mock_group

        self.mock_generate_transaction_id = patch(
            self, 'otter.rest.decorators.generate_transaction_id',
            return_value='transaction-id')

        # mock out modify state
        self.mock_state = mock.MagicMock(spec=[])  # so nothing can call it

        def _mock_modify_state(modifier, modify_state_reason=None,
                               *args, **kwargs):
            return defer.maybeDeferred(
                modifier, self.mock_group, self.mock_state, *args, **kwargs)

        self.mock_group.modify_state.side_effect = _mock_modify_state
        self.otter = Otter(self.mock_store, 'ord')
        self.root = self.otter.app.resource()

        # set pagination limits as it'll be used by all rest interfaces
        set_config_data({'limits': {'pagination': 100}, 'url_root': ''})
        self.addCleanup(set_config_data, {})

    def test_invalid_methods_are_405(self):
        """
        All methods other than GET return a 405: Forbidden Method
        """
        for method in self.invalid_methods:
            self.assert_status_code(405, method=method)


class AdminRestAPITestMixin(RequestTestMixin):
    """
    Mixin for setting up tests against the OtterAdmin REST API
    endpoints.
    """

    def setUp(self):
        """
        Mock out the data store and logger.
        """
        self.mock_store = iMock(IAdmin)

        self.mock_generate_transaction_id = patch(
            self, 'otter.rest.decorators.generate_transaction_id',
            return_value='a-wild-transaction-id')

        self.root = OtterAdmin(self.mock_store).app.resource()
