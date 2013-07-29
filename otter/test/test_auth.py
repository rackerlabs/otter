"""
Test authentication functions.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed, fail

from otter.test.utils import patch, SameJSON

from otter.util.http import APIError, RequestError

from otter.auth import authenticate_user
from otter.auth import extract_token
from otter.auth import impersonate_user
from otter.auth import endpoints_for_token
from otter.auth import user_for_tenant
from otter.auth import ImpersonatingAuthenticator

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
        extract_token will return the token ID of the auth response as a
        string.
        """
        resp = {'access': {'token': {'id': u'11111-111111-1111111-1111111'}}}
        self.assertEqual(extract_token(resp), '11111-111111-1111111-1111111')

    def test_authenticate_user(self):
        """
        authenticate_user sends the username and password to the tokens
        endpoint.
        """
        response = mock.Mock(code=200)
        response_body = {
            'access': {
                'token': {'id': '1111111111'}
            }
        }
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.post.return_value = succeed(response)

        d = authenticate_user('http://identity/v2.0', 'user', 'pass')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/v2.0/tokens',
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

        d = authenticate_user('http://identity/v2.0', 'user', 'pass')
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

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

        d = impersonate_user('http://identity/v2.0', 'auth-token', 'foo')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/v2.0/RAX-AUTH/impersonation-tokens',
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

        d = impersonate_user('http://identity/v2.0', 'auth-token', 'foo',
                             expire_in=60)

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/v2.0/RAX-AUTH/impersonation-tokens',
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

        d = impersonate_user('http://identity/v2.0', 'auth-token', 'foo',
                             expire_in=60)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

    def test_endpoints_for_token(self):
        """
        endpoints_for_token sends a properly formed request to the identity
        endpoint.
        """
        response = mock.Mock(code=200)
        response_body = {'endpoints': []}
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.get.return_value = succeed(response)

        d = endpoints_for_token('http://identity/v2.0', 'auth-token',
                                'user-token')

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.get.assert_called_once_with(
            'http://identity/v2.0/tokens/user-token/endpoints',
            headers=expected_headers)

    def test_endpoints_for_token_propogates_errors(self):
        """
        endpoints_for_token propagates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.get.return_value = succeed(response)

        d = endpoints_for_token('http://identity/v2.0', 'auth-token',
                                'user-token')
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

    def test_user_for_tenant(self):
        """
        user_for_tenant sends a properly formed request to the identity API for
        the list of users for a given tenant.
        """
        response = mock.Mock(code=200)
        response_body = {'user': {'id': 'ausername'}}
        self.treq.json_content.return_value = succeed(response_body)
        self.treq.get.return_value = succeed(response)

        d = user_for_tenant('http://identity/v2.0', 'username', 'password',
                            111111)

        self.assertEqual(self.successResultOf(d), 'ausername')

        self.treq.get.assert_called_once_with(
            'http://identity/v1.1/mosso/111111',
            auth=('username', 'password'),
            allow_redirects=False)

    def test_user_for_tenant_propagates_errors(self):
        """
        user_for_tenant propagates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.get.return_value = succeed(response)

        d = user_for_tenant('http://identity/v2.0', 'username', 'password',
                            111111)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')


class ImpersonatingAuthenticatorTests(TestCase):
    """
    Tests for the end-to-end impersonation workflow.
    """
    def setUp(self):
        """
        Shortcut by mocking all the helper functions that do IO.
        """
        self.authenticate_user = patch(self, 'otter.auth.authenticate_user')
        self.user_for_tenant = patch(self, 'otter.auth.user_for_tenant')
        self.impersonate_user = patch(self, 'otter.auth.impersonate_user')
        self.endpoints_for_token = patch(self,
                                         'otter.auth.endpoints_for_token')

        self.authenticate_user.return_value = succeed(
            {'access': {'token': {'id': 'auth-token'}}})
        self.user_for_tenant.return_value = succeed('test_user')
        self.impersonate_user.return_value = succeed(
            {'access': {'token': {'id': 'impersonation_token'}}})
        self.endpoints_for_token.return_value = succeed(
            {'endpoints': [{'name': 'anEndpoint', 'type': 'anType'}]})

        self.url = 'http://identity/v2.0'
        self.admin_url = 'http://identity_admin/v2.0'
        self.user = 'service_user'
        self.password = 'service_password'
        self.ia = ImpersonatingAuthenticator(self.user, self.password,
                                             self.url, self.admin_url)

    def test_authenticate_tenant_auth_as_service_user(self):
        """
        authenticate_tenant authenticates as the service user.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))

        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password)

    def test_authenticate_tenant_gets_user_for_specified_tenant(self):
        """
        authenticate_tenant gets user for the specified tenant from the admin
        endpoint.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))

        self.user_for_tenant.assert_called_once_with(self.admin_url, self.user,
                                                     self.password, 111111)

    def test_authenticate_tenant_impersonates_first_user(self):
        """
        authenticate_tenant impersonates the first user from the list of
        users for the tenant using the admin endpoint.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))

        self.impersonate_user.assert_called_once_with(self.admin_url,
                                                      'auth-token',
                                                      'test_user')

    def test_authenticate_tenant_gets_endpoints_for_the_impersonation_token(self):
        """
        authenticate_tenant fetches all the endpoints for the impersonation
        token.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))

        self.endpoints_for_token.assert_called_once_with(
            self.admin_url, 'auth-token', 'impersonation_token')

    def test_authenticate_tenant_returns_impersonation_token_and_endpoint_list(self):
        """
        authenticate_tenant returns the impersonation token and the endpoint
        list.
        """
        result = self.successResultOf(self.ia.authenticate_tenant(1111111))

        self.assertEqual(result[0], 'impersonation_token')
        self.assertEqual(result[1],
                         [{'name': 'anEndpoint',
                           'type': 'anType',
                           'endpoints': [
                               {'name': 'anEndpoint', 'type': 'anType'}]}])

    def test_authenticate_tenant_propagates_auth_errors(self):
        """
        authenticate_tenant propagates errors from authenticate_user.
        """
        self.authenticate_user.return_value = fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_user_list_errors(self):
        """
        authenticate_tenant propagates errors from user_for_tenant
        """
        self.user_for_tenant.return_value = fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_impersonation_errors(self):
        """
        authenticate_tenant propagates errors from impersonate_user
        """
        self.impersonate_user.return_value = fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_endpoint_list_errors(self):
        """
        authenticate_tenant propagates errors from endpoints_for_token
        """
        self.endpoints_for_token.return_value = fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))
