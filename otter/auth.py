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
from collections import defaultdict

from twisted.internet.defer import succeed, Deferred

import treq

from otter.util.http import (
    headers, check_success, append_segments, wrap_request_error)


class CachingAuthenticator(object):
    """
    An authenticator which cases the result of the provided auth_function
    based on the tenant_id.

    :param IReactorTime reactor: An IReactorTime provider used for enforcing
        the cache TTL.
    :param auth_function: A single-argument callable that returns a Deferred.
    :param int ttl: An integer indicating the TTL of a cache entry in seconds.
    """
    def __init__(self, reactor, auth_function, ttl):
        self._reactor = reactor
        self._auth_function = auth_function
        self._ttl = ttl

        self._waiters = defaultdict(list)
        self._cache = {}

    def authenticate_tenant(self, tenant_id):
        """
        Get an auth-token and service catalog for a tenant_id.  Possibly
        from a cache.

        :param tenant_id: The keystone tenant_id we wish to authenticate.
        :returns: a deferred that fires with a 2-tuple of auth-token and
            service catalog.

        """
        if tenant_id in self._cache:
            (created, data) = self._cache[tenant_id]
            now = self._reactor.seconds()

            if now - created <= self._ttl:
                return succeed(data)

        if tenant_id in self._waiters:
            d = Deferred()
            self._waiters[tenant_id].append(d)
            return d

        def when_authenticated(result):
            self._cache[tenant_id] = (self._reactor.seconds(), result)

            waiters = self._waiters.pop(tenant_id, [])
            for waiter in waiters:
                waiter.callback(result)

            return result

        d = self._auth_function(tenant_id)
        d.addCallback(when_authenticated)

        return d


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

    def authenticate_tenant(self, tenant_id):
        """
        :param tenant_id: The keystone tenant_id we wish to impersonate.
        :returns: a deferred that fires with a 2-tuple of auth-token and
            service catalog.
        """
        d = authenticate_user(self._url,
                              self._identity_admin_user,
                              self._identity_admin_password)
        d.addCallback(extract_token)

        def find_user(identity_admin_token):
            d = user_for_tenant(self._admin_url,
                                self._identity_admin_user,
                                self._identity_admin_password,
                                tenant_id)
            d.addCallback(lambda username: (identity_admin_token, username))
            return d

        d.addCallback(find_user)

        def impersonate((identity_admin_token, user)):
            iud = impersonate_user(self._admin_url,
                                   identity_admin_token,
                                   user)
            iud.addCallback(extract_token)
            iud.addCallback(lambda token: (identity_admin_token, token))
            return iud

        d.addCallback(impersonate)

        def endpoints((identity_admin_token, token)):
            scd = endpoints_for_token(self._admin_url, identity_admin_token, token)
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


def endpoints_for_token(auth_endpoint, identity_admin_token, user_token):
    """
    Get the list of endpoints from the service_catalog for the specified token.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str identity_admin_token: An Auth token for an identity admin user
        who can get the endpoints for a specified user token.
    :param str user_token: The user token to request endpoints for.

    :return: decoded JSON response as dict.
    """
    d = treq.get(append_segments(auth_endpoint, 'tokens', user_token, 'endpoints'),
                 headers=headers(identity_admin_token))
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, auth_endpoint, data='token_endpoints')
    d.addCallback(treq.json_content)
    return d


def user_for_tenant(auth_endpoint, username, password, tenant_id):
    """
    Use a super secret API to get the special actual username for a tenant id.

    :param str auth_endpoint: Identity Admin API endpoint.
    :param str username: A service username.
    :param str password: A service password.
    :param tenant_id: The tenant ID we wish to find the user for.

    :return: Username of the magical identity:user-admin user for the tenantid.
    """
    d = treq.get(
        append_segments(auth_endpoint.replace('v2.0', 'v1.1'), 'mosso', str(tenant_id)),
        auth=(username, password),
        allow_redirects=False)
    d.addCallback(check_success, [301])
    d.addErrback(wrap_request_error, auth_endpoint, data='mosso')
    d.addCallback(treq.json_content)
    d.addCallback(lambda user: user['user']['id'])
    return d


def authenticate_user(auth_endpoint, username, password):
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
        headers=headers())
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, auth_endpoint,
                 data=('authenticating', username))
    d.addCallback(treq.json_content)
    return d


def impersonate_user(auth_endpoint, identity_admin_token, username, expire_in=10800):
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
        headers=headers(identity_admin_token))
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
