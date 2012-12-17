"""Tests for the REST API"""

from collections import defaultdict, namedtuple
import json
from jsonschema import ValidationError

from klein.test_resource import requestMock

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web import server, http
from twisted.web.resource import getChildForRequest

from otter import scaling_groups_rest
from otter.models.interface import NoSuchScalingGroupError
from otter.test.utils import DeferredTestMixin
from otter.util.schema import InvalidJsonError

from otter.json_schema.scaling_group import (
    config_examples, launch_server_config_examples as launch_examples)


class DummyException(Exception):
    """
    A dummy exception to be passed around as if it was a real one.

    This way we are certain to throw a completely unhandled exception
    """
    pass


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


def request(method, endpoint, headers=None, body=None):
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

    resource = getChildForRequest(scaling_groups_rest.root, mock_request)
    return _render(resource, mock_request).addCallback(build_response)


class RestAPITestMixin(DeferredTestMixin):
    """
    Setup and teardown for tests for the REST API endpoints
    """

    def setUp(self):
        """
        Mock the interface

        :return: None
        """
        self.mock_store = mock.MagicMock()
        self.mock_groups = []
        for i in range(2):
            self.mock_groups.append(mock.MagicMock())
            self.mock_groups[-1].uuid = i
            self.mock_groups[-1].region = 'dfw'
            self.mock_groups[-1].name = 'bob'

        scaling_groups_rest.set_store(self.mock_store)

        self.mock_store.list_scaling_groups.return_value = {'dfw':
                                                            self.mock_groups}

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
            request(method, endpoint or self.endpoint, body=body))

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


class AllGroupsEndpointTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/autoscale`` endpoints
    """
    endpoint = "/v1.0/11111/autoscale"
    invalid_methods = ("DELETE", "PUT")

    def test_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_store.list_scaling_groups.return_value = defer.fail(error)
        self.assert_status_code(500)
        self.flushLoggedErrors()

    def test_no_groups_returns_empty_list(self):
        """
        If there are no groups for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        self.mock_store.list_scaling_groups.return_value = defer.succeed([])
        body = self.assert_status_code(200)
        self.mock_store.list_scaling_groups.assert_called_once_with('11111')
        self.assertEqual(json.loads(body), [])

    @mock.patch('otter.scaling_groups_rest.get_url_root', return_value="")
    def test_returned_group_list_gets_translated(self, mock_url):
        """
        Test that the scaling groups list gets translated into a list of
        scaling group ids and links.
        """
        # return two mock scaling group objects
        self.mock_store.list_scaling_groups.return_value = defer.succeed([
            mock.MagicMock(spec=['uuid'], uuid="1"),
            mock.MagicMock(spec=['uuid'], uuid="2")
        ])
        body = self.assert_status_code(200)
        self.mock_store.list_scaling_groups.assert_called_once_with('11111')
        self.assertEqual(json.loads(body), [
            {
                'id': '1',
                'links': [
                    {"href": '/v1.0/11111/autoscale/1', "rel": "self"},
                    {"href": '/11111/autoscale/1', "rel": "bookmark"}
                ]
            },
            {
                'id': '2',
                'links': [
                    {"href": '/v1.0/11111/autoscale/2', "rel": "self"},
                    {"href": '/11111/autoscale/2', "rel": "bookmark"}
                ]
            }
        ])

    def test_group_create_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed("one")
        self.assert_status_code(400, None, 'POST', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_group_create_invalid_schema_400(self):
        """
        Checks that the scaling groups schema is obeyed --
        an empty schema is bad.
        """

        self.mock_store.create_scaling_group.return_value = defer.succeed("one")
        response_body = self.assert_status_code(400, None, 'POST', '{}')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    @mock.patch('otter.scaling_groups_rest.get_url_root', return_value="")
    def test_group_create(self, mock_url):
        """
        Tries to create a scaling group
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed("one")
        request_body = {
            'groupConfiguration': config_examples[0],
            'launchConfiguration': launch_examples[0]
        }
        self.assert_status_code(201, None,
                                'POST', json.dumps(request_body),
                                '/v1.0/11111/autoscale/one')
        self.mock_store.create_scaling_group.assert_called_once_with(
            '11111', request_body)


class OneGroupTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/autoscale/{groupId}`` endpoints
    """
    endpoint = "/v1.0/11111/autoscale/one"
    invalid_methods = ("POST", "PUT")  # cannot update in bulk

    def test_group_delete(self):
        """
        Deleting an existing group succeeds with a 204.
        """
        self.mock_store.delete_scaling_group.return_value = defer.succeed(None)

        response_body = self.assert_status_code(204, method="DELETE")
        self.assertEqual(response_body, "")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            '11111', 'one')

    def test_group_delete_404(self):
        """
        Deleting a non-existant group fails with a 404.
        """
        self.mock_store.delete_scaling_group.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        response_body = self.assert_status_code(404, method="DELETE")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            '11111', 'one')

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)


class GroupConfigTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/autoscale/{groupId}/config`` endpoints
    """
    skip = "Not implemented yet."

    def test_group_get(self):
        """
        Tries to get a group
        """
        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.view_config.return_value = defer.succeed(request_body)

        self.mock_store.get_scaling_group.return_value = mock_group

        self.assert_status_code(200, self.endpoint + '/one', 'GET')

        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.view_config.assert_called_once_with()

    def test_group_get_404(self):
        """
        Tries to get a group, only to get a 404
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.view_config.return_value = defer.fail(
            NoSuchScalingGroupError('dfw', '11111', 'one'))

        self.mock_store.get_scaling_group.return_value = mock_group

        self.assert_status_code(404, self.endpoint + '/one', 'GET')

        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.view_config.assert_called_once_with()
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_group_modify(self):
        """
        Tries to modify a group
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = None

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(204, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw',
                                                                  'one')
        mock_group.update_config.assert_called_once_with(request_body)

    def test_group_modify_missing_input_400(self):
        """
        Checks that an invalid update won't be called
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = None

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {}

        response_body = self.assert_status_code(400, self.endpoint + '/one',
                                                'PUT',
                                                json.dumps(request_body))
        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')
        self.assertEqual(mock_group.update_config.called, False)
        self.flushLoggedErrors(ValidationError)

    def test_group_modify_not_found_404(self):
        """
        Checks that if you try to modify a not-found object it fails
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = defer.fail(
            NoSuchScalingGroupError('dfw', '11111', 'one'))

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(404, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        mock_group.update_config.assert_called_once_with(request_body)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_entity_modify_fail_500(self):
        """
        Checks to make sure that if the update fails for some strange
        reason, a 500 is returned
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = defer.fail(DummyException())

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(500, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.update_config.assert_called_once_with(request_body)
        self.flushLoggedErrors(DummyException)
