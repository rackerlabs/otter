"""
Test authentication functions.
"""
import mock

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed, fail, Deferred
from twisted.internet.task import Clock

from testtools.matchers import IsInstance

from zope.interface.verify import verifyObject

from otter.test.utils import patch, SameJSON, iMock, matches

from otter.util.http import APIError, RequestError

from otter.log import log as default_log

from otter.auth import authenticate_user
from otter.auth import get_admin_user
from otter.auth import extract_token
from otter.auth import impersonate_user
from otter.auth import endpoints_for_token
from otter.auth import user_for_tenant
from otter.auth import ImpersonatingAuthenticator
from otter.auth import CachingAuthenticator
from otter.auth import RetryingAuthenticator
from otter.auth import IAuthenticator

expected_headers = {'accept': ['application/json'],
                    'content-type': ['application/json'],
                    'x-auth-token': ['auth-token'],
                    'User-Agent': ['OtterScale/0.0']}


class HelperTests(SynchronousTestCase):
    """
    Test misc helpers for authentication.
    """
    def setUp(self):
        """
        Set up treq patch.
        """
        self.treq = patch(self, 'otter.auth.treq')
        patch(self, 'otter.util.http.treq', new=self.treq)
        self.log = mock.Mock()

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

        d = authenticate_user('http://identity/v2.0', 'user', 'pass',
                              log=self.log)

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
                     'content-type': ['application/json'],
                     'User-Agent': ['OtterScale/0.0']},
            log=self.log)

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

        d = impersonate_user('http://identity/v2.0', 'auth-token', 'foo',
                             log=self.log)

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.post.assert_called_once_with(
            'http://identity/v2.0/RAX-AUTH/impersonation-tokens',
            SameJSON({
                'RAX-AUTH:impersonation': {
                    'user': {'username': 'foo'},
                    'expire-in-seconds': 10800
                }
            }),
            headers=expected_headers,
            log=self.log)

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
            headers=expected_headers,
            log=None)

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
                                'user-token', log=self.log)

        self.assertEqual(self.successResultOf(d), response_body)

        self.treq.get.assert_called_once_with(
            'http://identity/v2.0/tokens/user-token/endpoints',
            headers=expected_headers, log=self.log)

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

    def test_get_admin_user(self):
        """
        :func:`get_admin_user` sends a properly formed request to the identity
        API to get the admin user for the given user, and returns the id of the
        admin user (which may be different than the given user's id).
        """
        response = mock.Mock(code=200)
        response_body = {"users": [{"id": "a_user_id"}]}

        self.treq.json_content.return_value = succeed(response_body)
        self.treq.get.return_value = succeed(response)

        d = get_admin_user('http://identity/v2.0', 'auth-token',
                           2222, log=self.log)

        self.assertEqual(self.successResultOf(d), 'a_user_id')

        self.treq.get.assert_called_once_with(
            'http://identity/v2.0/users/2222/RAX-AUTH/admins',
            headers=expected_headers,
            log=self.log)

    def test_get_admin_user_propagates_errors(self):
        """
        :func:`get_admin_user` propagates API errors.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.get.return_value = succeed(response)

        d = get_admin_user('http://identity/v2.0', 'auth-token', 2222)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

    def test_user_for_tenant_returns_singleton_user(self):
        """
        :func:`user_for_tenant` sends a properly formed request to the identity
        API for the list of users for a given tenant, and returns the id of
        the user immediately if there is a single user for that account.
        """
        response = mock.Mock(code=200)
        response_body = {"users": [{"id": "a_user_id"}]}

        self.treq.json_content.return_value = succeed(response_body)
        self.treq.get.return_value = succeed(response)

        d = user_for_tenant('http://identity/v2.0', 'auth-token',
                            111111, log=self.log)

        self.assertEqual(self.successResultOf(d), 'a_user_id')

        self.treq.get.assert_called_once_with(
            'http://identity/v2.0/tenants/111111/users',
            headers=expected_headers,
            log=self.log)

    def test_user_for_tenant_propagates_list_users_errors(self):
        """
        :func:`user_for_tenant` propagates API errors from listing users.
        """
        response = mock.Mock(code=500)
        self.treq.content.return_value = succeed('error_body')
        self.treq.get.return_value = succeed(response)

        d = user_for_tenant('http://identity/v2.0', 'auth-token', 111111)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

    def test_user_for_tenant_calls_get_admin_user_if_too_many_users(self):
        """
        :func:`user_for_tenant` sends a properly formed request to the identity
        API for the list of users for a given tenant, and if there is more than
        one user, gets the admin user for the first user in the list
        """
        response = mock.Mock(code=200)
        response_bodies = [
            {"users": [{"id": "not_admin1"}, {"id": "not_admin2"}]},  # list users
            {"users": [{"id": "admin_user"}]}  # get admin user
        ]

        self.treq.get.side_effect = lambda *a, **kw: succeed(response)
        self.treq.json_content.side_effect = (
            lambda _: succeed(response_bodies.pop(0)))

        d = user_for_tenant('http://identity/v2.0', 'auth-token',
                            111111, log=self.log)

        self.assertEqual(self.successResultOf(d), 'admin_user')

        self.assertEqual(
            self.treq.get.mock_calls,
            [mock.call('http://identity/v2.0/tenants/111111/users',
                       headers=expected_headers,
                       log=self.log),
             mock.call('http://identity/v2.0/users/not_admin1/RAX-AUTH/admins',
                       headers=expected_headers,
                       log=self.log)])

    def test_user_for_tenant_propagates_get_admin_user_errors(self):
        """
        :func:`user_for_tenant` propagates API errors from getting the admin
        user
        """
        responses = [mock.Mock(code=200), mock.Mock(code=500)]

        # response for list users
        self.treq.json_content.return_value = succeed(
            {"users": [{"id": "not_admin1"}, {"id": "not_admin2"}]})

        # response for get admin user
        self.treq.content.return_value = succeed('error_body')

        self.treq.get.side_effect = lambda *a, **kw: succeed(responses.pop(0))

        d = user_for_tenant('http://identity/v2.0', 'auth-token', 111111)
        failure = self.failureResultOf(d)

        self.assertTrue(failure.check(RequestError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')


class ImpersonatingAuthenticatorTests(SynchronousTestCase):
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

        self.authenticate_user.side_effect = lambda *a, **kw: succeed(
            {'access': {'token': {'id': 'auth-token'}}})
        self.user_for_tenant.side_effect = lambda *a, **kw: succeed('test_user')
        self.impersonate_user.side_effect = lambda *a, **kw: succeed(
            {'access': {'token': {'id': 'impersonation_token'}}})
        self.endpoints_for_token.side_effect = lambda *a, **kw: succeed(
            {'endpoints': [{'name': 'anEndpoint', 'type': 'anType'}]})

        self.url = 'http://identity/v2.0'
        self.admin_url = 'http://identity_admin/v2.0'
        self.user = 'service_user'
        self.password = 'service_password'
        self.ia = ImpersonatingAuthenticator(self.user, self.password,
                                             self.url, self.admin_url)
        self.log = mock.Mock()

    def test_verifyObject(self):
        """
        ImpersonatingAuthenticator provides the IAuthenticator interface.
        """
        verifyObject(IAuthenticator, self.ia)

    def test_authenticate_tenant_auth_as_service_user(self):
        """
        authenticate_tenant authenticates as the service user.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=None)

        self.authenticate_user.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=self.log)

    def test_authenticate_tenant_gets_user_for_specified_tenant(self):
        """
        authenticate_tenant gets user for the specified tenant from the admin
        endpoint.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.user_for_tenant.assert_called_once_with(self.admin_url,
                                                     'auth-token', 111111,
                                                     log=None)

        self.user_for_tenant.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))

        self.user_for_tenant.assert_called_once_with(self.admin_url,
                                                     'auth-token', 111111,
                                                     log=self.log)

    def test_authenticate_tenant_impersonates_first_user(self):
        """
        authenticate_tenant impersonates the first user from the list of
        users for the tenant using the admin endpoint.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.impersonate_user.assert_called_once_with(self.admin_url,
                                                      'auth-token',
                                                      'test_user', log=None)

        self.impersonate_user.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.impersonate_user.assert_called_once_with(self.admin_url,
                                                      'auth-token',
                                                      'test_user', log=self.log)

    def test_authenticate_tenant_gets_endpoints_for_the_impersonation_token(self):
        """
        authenticate_tenant fetches all the endpoints for the impersonation
        token.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.endpoints_for_token.assert_called_once_with(
            self.admin_url, 'auth-token', 'impersonation_token', log=None)

        self.endpoints_for_token.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.endpoints_for_token.assert_called_once_with(
            self.admin_url, 'auth-token', 'impersonation_token', log=self.log)

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
        self.authenticate_user.side_effect = lambda *a, **kw: fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_user_list_errors(self):
        """
        authenticate_tenant propagates errors from user_for_tenant
        """
        self.user_for_tenant.side_effect = lambda *a, **kw: fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_impersonation_errors(self):
        """
        authenticate_tenant propagates errors from impersonate_user
        """
        self.impersonate_user.side_effect = lambda *a, **kw: fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))

    def test_authenticate_tenant_propagates_endpoint_list_errors(self):
        """
        authenticate_tenant propagates errors from endpoints_for_token
        """
        self.endpoints_for_token.side_effect = lambda *a, **kw: fail(APIError(500, '500'))

        failure = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertTrue(failure.check(APIError))


class CachingAuthenticatorTests(SynchronousTestCase):
    """
    Test the in memory cache of authentication tokens.
    """
    def setUp(self):
        """
        Configure a clock and a fake auth function.
        """
        self.authenticator = iMock(IAuthenticator)

        def authenticate_tenant(tenant_id, log=None):
            return succeed(('auth-token', 'catalog'))

        self.authenticator.authenticate_tenant.side_effect = authenticate_tenant
        self.auth_function = self.authenticator.authenticate_tenant

        self.clock = Clock()
        self.ca = CachingAuthenticator(self.clock, self.authenticator, 10)

    def test_verifyObject(self):
        """
        CachingAuthenticator provides the IAuthenticator interface.
        """
        verifyObject(IAuthenticator, self.ca)

    def test_calls_auth_function_with_empty_cache(self):
        """
        authenticate_tenant with no items in the cache returns the result
        of the auth_function passed to the authenticator.
        """
        result = self.successResultOf(self.ca.authenticate_tenant(1, mock.Mock()))
        self.assertEqual(result, ('auth-token', 'catalog'))
        self.auth_function.assert_called_once_with(
            1, log=matches(IsInstance(mock.Mock)))

    def test_returns_token_from_cache(self):
        """
        authenticate_tenant returns tokens from the cache without calling
        auth_function again for subsequent calls.
        """
        result = self.successResultOf(self.ca.authenticate_tenant(1))
        self.assertEqual(result, ('auth-token', 'catalog'))

        result = self.successResultOf(self.ca.authenticate_tenant(1))
        self.assertEqual(result, ('auth-token', 'catalog'))

        self.auth_function.assert_called_once_with(
            1, log=matches(IsInstance(default_log.__class__)))

    def test_cache_expires(self):
        """
        authenticate_tenant will call auth_function again after the ttl has
        lapsed.
        """
        result = self.successResultOf(self.ca.authenticate_tenant(1))
        self.assertEqual(result, ('auth-token', 'catalog'))

        self.auth_function.assert_called_once_with(
            1, log=matches(IsInstance(default_log.__class__)))

        self.clock.advance(20)

        self.auth_function.side_effect = lambda _, log: succeed(('auth-token2', 'catalog2'))

        result = self.successResultOf(self.ca.authenticate_tenant(1))
        self.assertEqual(result, ('auth-token2', 'catalog2'))

        self.auth_function.assert_has_calls([
            mock.call(1, log=matches(IsInstance(default_log.__class__))),
            mock.call(1, log=matches(IsInstance(default_log.__class__)))])

    def test_serialize_auth_requests(self):
        """
        authenticate_tenant will serialize requests to authenticate the same
        tenant to prevent multiple outstanding auth requests when no
        value is cached.
        """
        auth_d = Deferred()
        self.auth_function.side_effect = lambda _, log: auth_d

        d1 = self.ca.authenticate_tenant(1)
        d2 = self.ca.authenticate_tenant(1)

        self.assertNotIdentical(d1, d2)

        self.auth_function.assert_called_once_with(
            1, log=matches(IsInstance(default_log.__class__)))

        auth_d.callback(('auth-token2', 'catalog2'))

        r1 = self.successResultOf(d1)
        r2 = self.successResultOf(d2)

        self.assertEqual(r1, r2)
        self.assertEqual(r1, ('auth-token2', 'catalog2'))

    def test_cached_value_per_tenant(self):
        """
        authenticate_tenant calls auth_function for each distinct tenant_id
        not found in the cache.
        """
        r1 = self.successResultOf(self.ca.authenticate_tenant(1))
        self.assertEqual(r1, ('auth-token', 'catalog'))

        self.auth_function.side_effect = (
            lambda _, log: succeed(('auth-token2', 'catalog2')))

        r2 = self.successResultOf(self.ca.authenticate_tenant(2))

        self.assertEqual(r2, ('auth-token2', 'catalog2'))

    def test_auth_failure_propagated_to_waiters(self):
        """
        authenticate_tenant propagates auth failures to all waiters
        """
        auth_d = Deferred()
        self.auth_function.side_effect = lambda _, log: auth_d

        d1 = self.ca.authenticate_tenant(1)
        d2 = self.ca.authenticate_tenant(1)

        self.assertNotIdentical(d1, d2)

        auth_d.errback(APIError(500, '500'))

        self.failureResultOf(d1)

        f2 = self.failureResultOf(d2)
        self.assertTrue(f2.check(APIError))

    def test_auth_failure_propagated_to_caller(self):
        """
        authenticate_tenant propagates auth failures to the caller.
        """
        self.auth_function.side_effect = lambda _, log: fail(APIError(500, '500'))

        d = self.ca.authenticate_tenant(1)
        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(APIError))


class RetryingAuthenticatorTests(SynchronousTestCase):
    """
    Tests for `RetryingAuthenticator`
    """

    def setUp(self):
        """
        Create RetryingAuthenticator
        """
        self.clock = Clock()
        self.mock_auth = iMock(IAuthenticator)
        self.authenticator = RetryingAuthenticator(
            self.clock, self.mock_auth, max_retries=3, retry_interval=4)

    def test_delegates(self):
        """
        `RetryingAuthenticator` calls internal authenticator and returns its result
        """
        self.mock_auth.authenticate_tenant.return_value = succeed('result')
        d = self.authenticator.authenticate_tenant(23)
        self.assertEqual(self.successResultOf(d), 'result')
        self.mock_auth.authenticate_tenant.assert_called_once_with(23, log=None)

    def test_retries(self):
        """
        `RetryingAuthenticator` retries internal authenticator if it fails
        """
        self.mock_auth.authenticate_tenant.side_effect = lambda *a, **kw: fail(APIError(500, '2'))
        d = self.authenticator.authenticate_tenant(23)
        # mock_auth is called and there is no result
        self.assertNoResult(d)
        self.mock_auth.authenticate_tenant.assert_called_once_with(23, log=None)
        # Advance clock and mock_auth is called again
        self.clock.advance(4)
        self.assertEqual(self.mock_auth.authenticate_tenant.call_count, 2)
        self.assertNoResult(d)
        # advance clock and mock_auth's success return is propogated
        self.mock_auth.authenticate_tenant.side_effect = lambda *a, **kw: succeed('result')
        self.clock.advance(4)
        self.assertEqual(self.successResultOf(d), 'result')

    def test_retries_times_out(self):
        """
        `RetryingAuthenticator` retries internal authenticator and times out if it
        keeps failing for certain period of time
        """
        self.mock_auth.authenticate_tenant.side_effect = lambda *a, **kw: fail(APIError(500, '2'))
        d = self.authenticator.authenticate_tenant(23)
        self.assertNoResult(d)
        self.clock.pump([4] * 4)
        f = self.failureResultOf(d, APIError)
        self.assertEqual(f.value.code, 500)
