"""
Utilities for testing the REST API, including a way of mock requesting a
response from the rest resource.
"""

from collections import defaultdict, namedtuple

from klein.test_resource import requestMock

import mock

from twisted.internet import defer
from twisted.web import server, http
from twisted.web.resource import getChildForRequest

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


ResponseWrapper = namedtuple('ResponseWrapper', ['response', 'content'])


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
    mock_request.code = None
    mock_request.setHeader = mock.MagicMock(spec=())

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
        response = mock.MagicMock(spec=['code', 'headers'], code=status_code,
                                  headers=http.Headers(headers))

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

        return ResponseWrapper(response=response, content=content)

    return _render(
        getChildForRequest(root_resource, mock_request),
        mock_request).addCallback(build_response)


class DummyException(Exception):
    """
    A dummy exception to be passed around as if it was a real one.

    This way we are certain to throw a completely unhandled exception
    """
    pass


class RestAPITestMixin(DeferredTestMixin):
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

        self.assertEqual(response_wrapper.response.code, expected_status)
        if location is not None:
            self.assertEqual(
                response_wrapper.response.headers.getRawHeaders('location'),
                [location])
        return response_wrapper.content

    def test_invalid_methods_are_405(self):
        """
        All methods other than GET return a 405: Forbidden Method
        """
        for method in self.invalid_methods:
            self.assert_status_code(405, method=method)
