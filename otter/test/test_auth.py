"""
Test authentication functions.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed

from otter.test.utils import patch, SameJSON

from otter.util.http import APIError

from otter.auth import authenticate_user
from otter.auth import extract_token
from otter.auth import impersonate_user
from otter.auth import endpoints_for_token


expected_headers = {'accept': ['application/json'],
                    'content-type': ['application/json'],
                    'x-auth-token': ['auth-token']}


class HelperTests(TestCase):
    """
    Test misc helpers for authentication.
    """
    def setUp(self):
        """
        Set up treq patch.
        """
        self.treq = patch(self, 'otter.auth.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)

    def test_extract_token(self):
        """
        extract_token will return the token ID of the auth response as a string.
        """
        resp = {'access': {'token': {'id': u'11111-111111-1111111-1111111'}}}
        self.assertEqual(extract_token(resp), '11111-111111-1111111-1111111')

    def test_authenticate_user(self):
        """
        authenticate_user sends the username and password to the tokens endpoint.
        """
        response = mock.Mock(code=200)
        response_body = {
            'access': {
                'token': {'id': '1111111111'}
            }
        }
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.post.return_value = succeed(response)

        d = authenticate_user('http://identity', 'user', 'pass')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/tokens',
            SameJSON({'auth': {
                'passwordCredentials': {
                    'username': 'user',
                    'password': 'pass'
                }
            }}),
            headers={'accept': ['application/json'],
                     'content-type': ['application/json']})

    def test_authenticate_user_propagates_error(self):
        """
        authenticate_user propogates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.post.return_value = succeed(response)

        d = authenticate_user('http://identity', 'user', 'pass')
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, 'error_body')

    def test_impersonate_user(self):
        """
        impersonate_user makes an impersonation request to the RAX-AUTH
        impersonation endpoint.
        """
        response = mock.Mock(code=200)
        response_body = {
            'access': {
                'token': {'id': '1111111111'}
            }
        }
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.post.return_value = succeed(response)

        d = impersonate_user('http://identity', 'auth-token', 'foo')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/RAX-AUTH/impersonation-tokens',
            SameJSON({
                'RAX-AUTH:impersonation': {
                    'user': {'username': 'foo'},
                    'expire-in-seconds': 10800
                }
            }),
            headers=expected_headers)

    def test_impersonate_user_expire_in_seconds(self):
        """
        impersonate_user sends it's expire_in keyword argument as the
        expire-in-seconds option.
        """
        response = mock.Mock(code=200)
        response_body = {
            'access': {
                'token': {'id': '1111111111'}
            }
        }
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.post.return_value = succeed(response)

        d = impersonate_user('http://identity', 'auth-token', 'foo', expire_in=60)

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/RAX-AUTH/impersonation-tokens',
            SameJSON({
                'RAX-AUTH:impersonation': {
                    'user': {'username': 'foo'},
                    'expire-in-seconds': 60
                }
            }),
            headers=expected_headers)

    def test_impersonate_user_propogates_errors(self):
        """
        impersonate_user propagates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.post.return_value = succeed(response)

        d = impersonate_user('http://identity', 'auth-token', 'foo', expire_in=60)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, 'error_body')

    def test_endpoints_for_token(self):
        """
        endpoints_for_token
        """
        response = mock.Mock(code=200)
        response_body = {'endpoints': []}
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.get.return_value = succeed(response)

        d = endpoints_for_token('http://identity', 'auth-token', 'user-token')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.get.assert_called_once_with(
            'http://identity/tokens/user-token/endpoints',
            headers=expected_headers)

    def test_endpoints_for_token_propogates_errors(self):
        """
        endpoints_for_token propagates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.get.return_value = succeed(response)

        d = endpoints_for_token('http://identity', 'auth-token', 'user-token')
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(APIError))
        self.assertEqual(failure.value.code, 500)
        self.assertEqual(failure.value.body, 'error_body')
