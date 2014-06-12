"""
Functions for interacting with the authentication API.

This module is primarily concerned with with impersonating customer accounts
and accessing the service catalog for those accounts to inform the worker
components about the location of API endpoints in a general way.

The current workflow for impersonating a customer is as follows:

#. Authenticate as our service account (username: autoscale)
#. Given a tenant ID

 #. Find a user for that tenant ID.
    NOTE: Currently tenants only have a single user.  In a multi-user future,
    we'll need to find a user that has the appropriate capabilities to execute
    the scaling policy, so the ability create/destroy servers and add/remove
    nodes from load balancers.  This will require getting the list of users,
    and for each user requesting their roles.

    In a good multi-user future tenants that wish to use autoscaling
    should just give the appropriate roles to an autoscale user. Instead of
    requiring impersonation.

 #. Impersonate the user by name.
 #. Retrieve a service catalog (the list of API endpoitns) for the user by
    token ID.

The implemented workflow uses only v2.0 APIs and so it makes some assumptions
about the featureset of the world.  It currently chooses the first (and only)
user for a tenant and impersonates them.  There is a mosso API in Identity Admin
v1.1 that can give you a single (probably default) user for a given tenant but
it is not currently being used.

This API also currently makes use of features of the Identity Admin v2.0 API
that are only availabe in staging (listing users for a tenant, and endpoints for
a token.)
"""

import json
from itertools import groupby
from functools import partial

from twisted.internet.defer import succeed, Deferred

from zope.interface import Interface, implementer

from otter.util import logging_treq as treq
from otter.util.retry import retry, retry_times, repeating_interval

from otter.log import log as default_log
from otter.util.http import (
    headers, check_success, append_segments, wrap_request_error)


class IAuthenticator(Interface):
    """
    Authenticators know how to authenticate tenants.
    """
    def authenticate_tenant(tenant_id, log=None):
        """
        :param tenant_id: A keystone tenant ID to authenticate as.

        :returns: 2-tuple of auth token and service catalog.
        """


@implementer(IAuthenticator)
class RetryingAuthenticator(object):
    """
    An authenticator that retries the provided auth_function if it fails

    :param IReactorTime reactor: An IReactorTime provider used for retrying
    :param IAuthenticator authenticator: retry authentication using this
    """
    def __init__(self, reactor, authenticator, max_retries=10, retry_interval=10):
        self._reactor = reactor
        self._authenticator = authenticator
        self._max_retries = max_retries
        self._retry_interval = retry_interval

    def authenticate_tenant(self, tenant_id, log=None):
        """
        see :meth:`IAuthenticator.authenticate_tenant`
        """
        return retry(
            partial(self._authenticator.authenticate_tenant, tenant_id, log=log),
            can_retry=retry_times(self._max_retries),
            next_interval=repeating_interval(self._retry_interval),
            clock=self._reactor)


@implementer(IAuthenticator)
class CachingAuthenticator(object):
    """
    An authenticator which cases the result of the provided auth_function
    based on the tenant_id.

    :param IReactorTime reactor: An IReactorTime provider used for enforcing
        the cache TTL.
    :param IAuthenticator authenticator:
    :param int ttl: An integer indicating the TTL of a cache entry in seconds.
    """
    def __init__(self, reactor, authenticator, ttl):
        self._reactor = reactor
        self._authenticator = authenticator
        self._ttl = ttl

        self._waiters = {}
        self._cache = {}
        self._log = self._bind_log(default_log)

    def _bind_log(self, log, **kwargs):
        """
        Binds relevant authenticator arguments to a `BoundLog`
        """
        return log.bind(system='otter.auth.cache',
                        authenticator=self._authenticator,
                        cache_ttl=self._ttl,
                        **kwargs)

    def authenticate_tenant(self, tenant_id, log=None):
        """
        see :meth:`IAuthenticator.authenticate_tenant`
        """
        if log is None:
            log = self._log.bind(tenant_id=tenant_id)
        else:
            log = self._bind_log(log, tenant_id=tenant_id)

        if tenant_id in self._cache:
            (created, data) = self._cache[tenant_id]
            now = self._reactor.seconds()

            if now - created <= self._ttl:
                log.msg('otter.auth.cache.hit', age=now - created)
                return succeed(data)

            log.msg('otter.auth.cache.expired', age=now - created)

        if tenant_id in self._waiters:
            d = Deferred()
            self._waiters[tenant_id].append(d)
            log.msg('otter.auth.cache.waiting',
                    waiters=len(self._waiters[tenant_id]))
            return d

        def when_authenticated(result):
            log.msg('otter.auth.cache.populate')
            self._cache[tenant_id] = (self._reactor.seconds(), result)

            waiters = self._waiters.pop(tenant_id, [])
            for waiter in waiters:
                waiter.callback(result)

            return result

        def when_auth_fails(failure):
            waiters = self._waiters.pop(tenant_id, [])
            for waiter in waiters:
                waiter.errback(failure)

            return failure

        log.msg('otter.auth.cache.miss')
        self._waiters[tenant_id] = []
        d = self._authenticator.authenticate_tenant(tenant_id, log=log)
        d.addCallback(when_authenticated)
        d.addErrback(when_auth_fails)

        return d


@implementer(IAuthenticator)
class ImpersonatingAuthenticator(object):
    """
    An authentication handler that first uses a identity admin account to authenticate
    and then impersonates the desired tenant_id.
    """
    def __init__(self, identity_admin_user, identity_admin_password, url, admin_url):
        self._identity_admin_user = identity_admin_user
        self._identity_admin_password = identity_admin_password
        self._url = url
        self._admin_url = admin_url

    def authenticate_tenant(self, tenant_id, log=None):
        """
        see :meth:`IAuthenticator.authenticate_tenant`
        """
        d = authenticate_user(self._url,
                              self._identity_admin_user,
                              self._identity_admin_password,
                              log=log)
        d.addCallback(extract_token)

        def find_user(identity_admin_token):
            d = user_for_tenant(self._admin_url,
                                identity_admin_token,
                                tenant_id, log=log)
            d.addCallback(lambda username: (identity_admin_token, username))
            return d

        d.addCallback(find_user)

        def impersonate((identity_admin_token, user)):
            iud = impersonate_user(self._admin_url,
                                   identity_admin_token,
                                   user, log=log)
            iud.addCallback(extract_token)
            iud.addCallback(lambda token: (identity_admin_token, token))
            return iud

        d.addCallback(impersonate)

        def endpoints((identity_admin_token, token)):
            scd = endpoints_for_token(self._admin_url, identity_admin_token,
                                      token, log=log)
            scd.addCallback(lambda endpoints: (token, _endpoints_to_service_catalog(endpoints)))
            return scd

        d.addCallback(endpoints)

        return d


def extract_token(auth_response):
    """
    Extract an auth token from an authentication response.

    :param dict auth_response: A dictionary containing the decoded response
        from the authentication API.
    :rtype: str
    """
    return auth_response['access']['token']['id'].encode('ascii')


def endpoints_for_token(auth_endpoint, identity_admin_token, user_token,
                        log=None):
    """
    Get the list of endpoints from the service_catalog for the specified token.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str identity_admin_token: An Auth token for an identity admin user
        who can get the endpoints for a specified user token.
    :param str user_token: The user token to request endpoints for.

    :return: decoded JSON response as dict.
    """
    d = treq.get(append_segments(auth_endpoint, 'tokens', user_token, 'endpoints'),
                 headers=headers(identity_admin_token), log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, auth_endpoint, data='token_endpoints')
    d.addCallback(treq.json_content)
    return d


def get_admin_user(auth_endpoint, identity_admin_token, user_id, log=None):
    """
    Given a user ID, gets that user's tenant's admin user.  That is, the admin
    user for the tenant account of the user with the given user id.

    :param str auth_endpoint: Identity Admin API endpoint.
    :param str identity_admin_token: An Auth token for an identity admin user
        who can get the endpoints for a specified user token.
    :param user_id: The user ID we wish to find the admin user for.
    """
    d = treq.get(
        append_segments(auth_endpoint, 'users', str(user_id),
                        'RAX-AUTH', 'admins'),
        headers=headers(identity_admin_token), log=log)

    d.addCallback(check_success, [200])
    d.addErrback(wrap_request_error, auth_endpoint,
                 data='admin_user_for_user')
    d.addCallback(treq.json_content)
    d.addCallback(lambda b: b['users'][0]['username'])
    return d


def user_for_tenant(auth_endpoint, identity_admin_token, tenant_id, log=None):
    """
    Use the internal API to get the admin username for a tenant.  This involves:

    1. Listing the users for that tenant.  If there is only 1 user, then that
        is the admin user for that tenant. (see
        )

    2. If there is more than 1 user, grab the first user, and use that user
        ID to get the admin account for that tenant via an admin user API.

    Note that this returns the username, not a user ID.  Getting the admin
    user requires the admin ID, however.

    :param str auth_endpoint: Identity Admin API endpoint.
    :param str identity_admin_token: An Auth token for an identity admin user
        who can get the endpoints for a specified user token.
    :param tenant_id: The tenant ID we wish to find the user for.

    :return: Username of the magical identity:user-admin user for the tenantid.
    """
    def check_users(json_blob):
        users = json_blob['users']
        if len(users) == 1:
            return users[0]['username']

        return get_admin_user(auth_endpoint, identity_admin_token,
                              users[0]['id'], log)

    d = treq.get(
        append_segments(auth_endpoint, 'tenants', str(tenant_id), 'users'),
        headers=headers(identity_admin_token), log=log)
    d.addCallback(check_success, [200])
    d.addErrback(wrap_request_error, auth_endpoint,
                 data='listing_users_for_tenant')
    d.addCallback(treq.json_content)
    d.addCallback(check_users)
    return d


def authenticate_user(auth_endpoint, username, password, log=None):
    """
    Authenticate to a Identity auth endpoint with a username and password.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str username: Username to authenticate as.
    :param str password: Password for the specified user.

    :return: Decoded JSON response as dict.
    """
    d = treq.post(
        append_segments(auth_endpoint, 'tokens'),
        json.dumps(
            {
                "auth": {
                    "passwordCredentials": {
                        "username": username,
                        "password": password
                    }
                }
            }),
        headers=headers(),
        log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, auth_endpoint,
                 data=('authenticating', username))
    d.addCallback(treq.json_content)
    return d


def impersonate_user(auth_endpoint, identity_admin_token, username,
                     expire_in=10800, log=None):
    """
    Acquire an auth-token for a user via impersonation.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str identity_admin_token: Auth token that has the appropriate
        permissions to impersonate other users.
    :param str username: Username to impersonate.
    :param str expire_in: Number of seconds for which the token will be valid.

    :return: Decoded JSON as dict.
    """
    d = treq.post(
        append_segments(auth_endpoint, 'RAX-AUTH', 'impersonation-tokens'),
        json.dumps({
            "RAX-AUTH:impersonation": {
                "user": {"username": username},
                "expire-in-seconds": expire_in
            }
        }),
        headers=headers(identity_admin_token),
        log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, auth_endpoint, data='impersonation')
    d.addCallback(treq.json_content)
    return d


def _endpoints_to_service_catalog(endpoints):
    """
    Convert the endpoint list from the endpoints API to the service catalog format
    from the authentication API.
    """
    return [{'endpoints': list(e), 'name': n, 'type': t}
            for (n, t), e in groupby(endpoints['endpoints'], lambda i: (i['name'], i['type']))]
