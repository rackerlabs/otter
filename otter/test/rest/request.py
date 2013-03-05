"""
Utilities for testing the REST API, including a way of mock requesting a
response from the rest resource.
"""

from collections import defaultdict, namedtuple
from urlparse import urlsplit

from klein.test_resource import requestMock

import mock

from twisted.internet import defer
from twisted.web import server, http
from twisted.web.resource import getChildForRequest
from twisted.web.server import Request

from otter.models.interface import IScalingGroup, IScalingGroupCollection
from otter.rest.application import root, set_store
from otter.test.utils import iMock, DeferredTestMixin


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
    # build mock request
    mock_request = requestMock(endpoint, method, headers=headers, body=body)
    # because the first one is empty, it breaks getChildForRequest
    mock_request.postpath.pop(0)

    # these are used when writing the response
    mock_request.code = 200
    mock_request.setHeader = mock.MagicMock(spec=())

    # if setHeader has been called a with unicode value, twisted will raise a
    # TypeError after the request has been closed and it is attemptig to write
    # to the network.  So just fail here for testing purposes
    def _twisted_compat(name, value):
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("Can only pass-through bytes on Python 2")

    mock_request.setHeader.side_effect = _twisted_compat

    def build_response(_):
        # build a response that offers some useful attributes of an IResponse
        status_code = 200
        if mock_request.setResponseCode.call_args is not None:
            # first non-keyword arg - getting it from call_args means the non
            # kwargs are the first argument, not the second
            status_code = mock_request.setResponseCode.call_args[0][0]

        headers = defaultdict(list)
        for call in mock_request.setHeader.mock_calls:
            # setHeader(name, value)
            # a call in mock_calls is a tuple of (name, args, kwargs))
            headers[call[1][0]].append(call[1][1])
        headers = http.Headers(headers)

        # if the content-type has not been set, Twisted by default sets the
        # content-type to be whatever is in
        # twisted.web.server.Request.defaultContentType, so replicate that
        # functionality
        if not (headers.hasHeader('Content-Type') or
                Request.defaultContentType is None):
            headers.setRawHeaders('Content-Type', [Request.defaultContentType])

        response = mock.MagicMock(spec=['code', 'headers'], code=status_code,
                                  headers=headers)

        # Annoying implementation detail: if the status code is one of the
        # status codes that should not have a body, twisted replaces the
        # write method of the request with a function that does nothing, so
        # no response body can every be written.  This messes up the mock
        # request's write function (which just returns another mock.  So
        # in this case, just return "".
        content = ''
        if status_code not in http.NO_BODY_CODES:
            # get the body by joining all calls to request.write
            content = "".join(
                [call[1][0] for call in mock_request.write.mock_calls])

        return ResponseWrapper(response=response, content=content, request=mock_request)

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
    pass


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
        if expected_status not in [405, 301]:
            self.assertNotEqual(headers.getRawHeaders('X-Response-ID'), None)
            self.assertEqual(headers.getRawHeaders('Content-Type'),
                             ['application/json'])
        else:
            content_type = headers.getRawHeaders('Content-Type')[0]
            self.assertIn('text/html', content_type)

        error_message = [
            "Got status {0} but expected {1}".format(
                response_wrapper.response.code, expected_status),
            "Response: {0}".format(response_wrapper.content)]
        if message:
            error_message.insert(0, message)

        self.assertEqual(response_wrapper.response.code, expected_status,
                         "\n".join(error_message))

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


class RestAPITestMixin(DeferredTestMixin, RequestTestMixin):
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

        set_store(self.mock_store)

    def assert_status_code(self, expected_status, endpoint=None,
                           method="GET", body="", location=None):
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
        response_wrapper = self.assert_deferred_succeeded(
            request(root, method, endpoint or self.endpoint, body=body))

        self.assert_response(response_wrapper, expected_status)
        if location is not None:
            self.assertEqual(self.get_location_header(response_wrapper),
                             location)
        return response_wrapper.content

    def test_invalid_methods_are_405(self):
        """
        All methods other than GET return a 405: Forbidden Method
        """
        for method in self.invalid_methods:
            self.assert_status_code(405, method=method)

    def test_non_trailing_slash_redirects_to_trailing_slash(self):
        """
        Trying to hit the non-trailing-slash version of the URL results in a
        redirect to the trailing slash version
        """
        self.assertTrue(self.endpoint.endswith('/'),
                        "The default endpoint should have a trailing slash: {0}".format(
                            self.endpoint))

        # HEAD works even if it's not listed in the available methods, but
        # but that's handled elsewhere (probably in Twisted), so we can't use
        # it for testing here.  So find a method that is not invalid, and use
        # that.
        for method in ('GET', 'PUT', 'POST', 'DELETE'):
            if not method in self.invalid_methods:
                self.assert_status_code(301, method=method,
                                        endpoint=self.endpoint.rstrip('/'))
