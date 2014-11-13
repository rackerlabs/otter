"""
Test authentication functions.
"""
import mock
from copy import deepcopy

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed, fail, Deferred
from twisted.python.failure import Failure
from twisted.internet.task import Clock

from testtools.matchers import IsInstance

from zope.interface.verify import verifyObject

from otter.test.utils import patch, SameJSON, iMock, matches

from otter.util.http import APIError, UpstreamError

from otter.log import log as default_log

from otter.auth import (authenticate_user, extract_token, impersonate_user,
                        endpoints_for_token, user_for_tenant,
                        ImpersonatingAuthenticator,
                        CachingAuthenticator, RetryingAuthenticator,
                        WaitingAuthenticator, IAuthenticator,
                        endpoints, public_endpoint_url, generate_authenticator)


expected_headers = {'accept': ['application/json'],
                    'content-type': ['application/json'],
                    'x-auth-token': ['auth-token'],
                    'User-Agent': ['OtterScale/0.0']}

fake_service_catalog = [
    {'type': 'compute',
     'name': 'cloudServersOpenStack',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.openstack/'},
         {'region': 'ORD', 'publicURL': 'http://ord.openstack/'}
     ]},
    {'type': 'lb',
     'name': 'cloudLoadBalancers',
     'endpoints': [
         {'region': 'DFW', 'publicURL': 'http://dfw.lbaas/'},
     ]}
]


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

        self.assertTrue(failure.check(UpstreamError))
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

        self.assertTrue(failure.check(UpstreamError))
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

        self.assertTrue(failure.check(UpstreamError))
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
                            111111, log=self.log)

        self.assertEqual(self.successResultOf(d), 'ausername')

        self.treq.get.assert_called_once_with(
            'http://identity/v1.1/mosso/111111',
            auth=('username', 'password'),
            allow_redirects=False, log=self.log)

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

        self.assertTrue(failure.check(UpstreamError))
        real_failure = failure.value.reason

        self.assertTrue(real_failure.check(APIError))
        self.assertEqual(real_failure.value.code, 500)
        self.assertEqual(real_failure.value.body, 'error_body')

    def test_endpoints(self):
        """
        endpoints will return only the named endpoint in a specific region.
        """
        self.assertEqual(
            sorted(endpoints(fake_service_catalog,
                             'cloudServersOpenStack',
                             'DFW')),
            [{'region': 'DFW', 'publicURL': 'http://dfw.openstack/'}])

    def test_public_endpoint_url(self):
        """
        public_endpoint_url returns the first publicURL for the named service
        in a specific region.
        """
        self.assertEqual(
            public_endpoint_url(fake_service_catalog, 'cloudServersOpenStack',
                                'DFW'),
            'http://dfw.openstack/')


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

    def test_auth_me_auth_as_service_user(self):
        """
        _auth_me authenticates as the service user.
        """
        self.successResultOf(self.ia._auth_me(None))
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=None)
        self.assertEqual(self.ia._token, 'auth-token')
        self.assertFalse(self.log.msg.called)

        self.authenticate_user.reset_mock()

        self.successResultOf(self.ia._auth_me(self.log))
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=self.log)
        self.log.msg.assert_called_once_with('Getting new identity admin token')
        self.assertEqual(self.ia._token, 'auth-token')

    def test_authenticate_tenant_gets_user_for_specified_tenant(self):
        """
        authenticate_tenant gets user for the specified tenant from the admin
        endpoint.
        """
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.user_for_tenant.assert_called_once_with(self.admin_url, self.user,
                                                     self.password, 111111,
                                                     log=None)

        self.user_for_tenant.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))

        self.user_for_tenant.assert_called_once_with(self.admin_url, self.user,
                                                     self.password, 111111,
                                                     log=self.log)

    def test_authenticate_tenant_impersonates_first_user(self):
        """
        authenticate_tenant impersonates the first user from the list of
        users for the tenant using the admin endpoint.
        """
        self.ia._token = 'auth-token'
        self.successResultOf(self.ia.authenticate_tenant(111111))
        self.impersonate_user.assert_called_once_with(self.admin_url,
                                                      'auth-token',
                                                      'test_user', log=None)

        self.impersonate_user.reset_mock()

        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.impersonate_user.assert_called_once_with(self.admin_url,
                                                      'auth-token',
                                                      'test_user', log=self.log)

    def test_authenticate_tenant_retries_impersonates_first_user(self):
        """
        authenticate_tenant impersonates again with new auth if initial impersonation
        fails with 401
        """
        self.impersonate_user.side_effect = [
            fail(UpstreamError(Failure(APIError(401, '')), 'identity', 'o')),
            succeed({'access': {'token': {'id': 'impersonation_token'}}})]
        self.successResultOf(self.ia.authenticate_tenant(111111, self.log))
        self.impersonate_user.assert_has_calls(
            [mock.call(self.admin_url, None, 'test_user', log=self.log),
             mock.call(self.admin_url, 'auth-token', 'test_user', log=self.log)])
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=self.log)
        self.log.msg.assert_called_once_with('Getting new identity admin token')

    def test_authenticate_tenant_gets_endpoints_for_the_impersonation_token(self):
        """
        authenticate_tenant fetches all the endpoints for the impersonation with
        cached token.
        """
        self.ia._token = 'auth-token'
        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.endpoints_for_token.assert_called_once_with(
            self.admin_url, 'auth-token', 'impersonation_token', log=self.log)

    def test_authenticate_tenant_retries_getting_endpoints_for_the_impersonation_token(self):
        """
        authenticate_tenant fetches all the endpoints for the impersonation and
        retries with new authentication token if it gets 401
        """
        self.endpoints_for_token.side_effect = [
            fail(UpstreamError(Failure(APIError(401, '')), 'identity', 'o')),
            succeed({'endpoints': [{'name': 'anEndpoint', 'type': 'anType'}]})]
        self.successResultOf(self.ia.authenticate_tenant(111111, log=self.log))
        self.endpoints_for_token.assert_has_calls(
            [mock.call(self.admin_url, None, 'impersonation_token', log=self.log),
             mock.call(self.admin_url, 'auth-token', 'impersonation_token', log=self.log)])
        self.authenticate_user.assert_called_once_with(self.url, self.user,
                                                       self.password,
                                                       log=self.log)
        self.log.msg.assert_called_once_with('Getting new identity admin token')

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
        self.impersonate_user.side_effect = lambda *a, **k: fail(
            UpstreamError(Failure(APIError(401, '4')), 'identity', 'o'))
        self.authenticate_user.side_effect = lambda *a, **kw: fail(
            UpstreamError(Failure(APIError(500, '500')), 'identity', 'o'))

        f = self.failureResultOf(self.ia.authenticate_tenant(111111), UpstreamError)
        self.assertEqual(f.value.reason.value.code, 500)

    def test_authenticate_tenant_propagates_user_list_errors(self):
        """
        authenticate_tenant propagates errors from user_for_tenant
        """
        self.user_for_tenant.side_effect = lambda *a, **kw: fail(
            UpstreamError(Failure(APIError(500, '500')), 'identity', 'o'))

        f = self.failureResultOf(self.ia.authenticate_tenant(111111), UpstreamError)
        self.assertEqual(f.value.reason.value.code, 500)

    def test_authenticate_tenant_propagates_impersonation_errors(self):
        """
        authenticate_tenant propagates errors from impersonate_user
        """
        self.impersonate_user.side_effect = lambda *a, **kw: fail(
            UpstreamError(Failure(APIError(500, '500')), 'identity', 'o'))

        f = self.failureResultOf(self.ia.authenticate_tenant(111111))
        self.assertEqual(f.value.reason.value.code, 500)

    def test_authenticate_tenant_propagates_endpoint_list_errors(self):
        """
        authenticate_tenant propagates errors from endpoints_for_token
        """
        self.endpoints_for_token.side_effect = lambda *a, **kw: fail(
            UpstreamError(Failure(APIError(500, '500')), 'identity', 'o'))

        f = self.failureResultOf(self.ia.authenticate_tenant(111111), UpstreamError)
        self.assertEqual(f.value.reason.value.code, 500)


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

    def test_invalidate(self):
        """
        The invalidate method causes the next authenticate_tenant call to
        re-authenticate.
        """
        self.ca.authenticate_tenant(1)
        self.ca.invalidate(1)
        self.ca.authenticate_tenant(1)
        self.auth_function.assert_has_calls([
            mock.call(1, log=matches(IsInstance(default_log.__class__))),
            mock.call(1, log=matches(IsInstance(default_log.__class__)))])


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


class WaitingAuthenticatorTests(SynchronousTestCase):
    """
    Tests for `WaitingAuthenticator`
    """

    def setUp(self):
        """
        Create WaitingAuthenticator
        """
        self.clock = Clock()
        self.mock_auth = iMock(IAuthenticator)
        self.authenticator = WaitingAuthenticator(self.clock, self.mock_auth, 5)

    def test_waits(self):
        """
        Waits before returning token
        """
        self.mock_auth.authenticate_tenant.return_value = succeed('token')
        d = self.authenticator.authenticate_tenant('t1', 'log')
        self.assertNoResult(d)
        self.clock.advance(5)
        self.assertEqual(self.successResultOf(d), 'token')
        self.mock_auth.authenticate_tenant.assert_called_once_with('t1', log='log')

    def test_no_wait_on_error(self):
        """
        Does not wait if internal auth errors
        """
        self.mock_auth.authenticate_tenant.return_value = fail(ValueError('e'))
        d = self.authenticator.authenticate_tenant('t1', 'log')
        self.failureResultOf(d, ValueError)


identity_config = {
    'username': 'uname', 'password': 'pwd', 'url': 'htp',
    'admin_url': 'ad', 'max_retries': 3, 'retry_interval': 5,
    'wait': 4, 'cache_ttl': 50
}


class AuthenticatorTests(SynchronousTestCase):
    """
    Check if authenticators are instantiated in right composition
    """

    def setUp(self):
        """
        Config with identity settings
        """
        self.config = deepcopy(identity_config)

    def test_composition(self):
        """
        authenticator is composed correctly with values from config
        """
        r = mock.Mock()
        a = generate_authenticator(r, self.config)
        self.assertIsInstance(a, CachingAuthenticator)
        self.assertIdentical(a._reactor, r)
        self.assertEqual(a._ttl, 50)

        wa = a._authenticator
        self.assertIsInstance(wa, WaitingAuthenticator)
        self.assertIdentical(wa._reactor, r)
        self.assertEqual(wa._wait, 4)

        ra = wa._authenticator
        self.assertIsInstance(ra, RetryingAuthenticator)
        self.assertIdentical(ra._reactor, r)
        self.assertEqual(ra._max_retries, 3)
        self.assertEqual(ra._retry_interval, 5)

        ia = ra._authenticator
        self.assertIsInstance(ia, ImpersonatingAuthenticator)
        self.assertEqual(ia._identity_admin_user, 'uname')
        self.assertEqual(ia._identity_admin_password, 'pwd')
        self.assertEqual(ia._url, 'htp')
        self.assertEqual(ia._admin_url, 'ad')

    def test_wait_defaults(self):
        """
        WaitingAuthenticator is created with default of 5 if not given
        """
        del self.config['wait']
        r = mock.Mock()
        a = generate_authenticator(r, self.config)
        self.assertEqual(a._authenticator._wait, 5)

    def test_cache_ttl_defaults(self):
        """
        CachingAuthenticator is created with default of 300 if not given
        """
        del self.config['cache_ttl']
        r = mock.Mock()
        a = generate_authenticator(r, self.config)
        self.assertEqual(a._ttl, 300)
