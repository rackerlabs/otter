"""
Functions for interacting with the authentication API.
"""

import json
import treq

from otter.util.config import config_value
from otter.util.http import headers, check_success, append_segments


def authenticate_tenant(tenant_id):
    """
    Authenticate as the desired tenant.

    :params tenant_id: id of the tenant to authenticate as
    :returns: Deferred that fires with a 2-tuple of auth token and service catalog.
    """
    ia = _ImpersonatingAuthenticator(config_value('identity.username'),
                                     config_value('identity.password'),
                                     config_value('identity.url'),
                                     config_value('identity.admin_url'))
    return ia.authenticate_tenant(tenant_id)


class _ImpersonatingAuthenticator(object):
    """
    An authentication handler that first uses a service account to authenticate
    and then impersonates the desired tenant_id.
    """
    def __init__(self, service_user, service_password, url, admin_url):
        self._service_user = service_user
        self._service_password = service_password

        # XXX: TODO: This is not the correct way to deal with unicode URLs.
        # Maybe append_segments should support it better.
        self._url = url.encode('ascii')
        self._admin_url = admin_url.encode('ascii')

    def authenticate_tenant(self, tenant_id):
        """
        :param tenant_id: The keystone tenant_id we wish to impersonate.
        :returns: a deferred that fires with a 2-tuple of auth-token and
            service catalog.
        """
        d = authenticate_user(self._url,
                              self._service_user,
                              self._service_password)
        d.addCallback(extract_token)

        def find_user(impersonator_token):
            return users_for_tenant(
                self._admin_url,
                impersonator_token,
                tenant_id).addCallback(
                    lambda users: (impersonator_token, users['users'][0]['username']))

        d.addCallback(find_user)

        def impersonate((impersonator_token, user)):
            iud = impersonate_user(self._admin_url,
                                   impersonator_token,
                                   user)
            iud.addCallback(extract_token)
            iud.addCallback(lambda token: (impersonator_token, token))
            return iud

        d.addCallback(impersonate)

        def endpoints((impersonator_token, token)):
            scd = endpoints_for_token(self._admin_url, impersonator_token, token)
            scd.addCallback(lambda catalog: (token, catalog.get('endpoints', [])))
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
    d.addCallback(treq.json_content)
    return d


def users_for_tenant(auth_endpoint, identity_admin_token, tenant_id):
    """
    Retrieve all users for the specified tenant.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str identity_admin_token: An Auth token for an identity admin user
        who can get the endpoints for a specified user token.
    :param tenant_id: The tenant ID we wish to find a user for.

    :return: Decoded JSON response as dict.
    """
    d = treq.get(
        append_segments(auth_endpoint, 'tenants', str(tenant_id), 'users'),
        headers=headers(identity_admin_token))
    d.addCallback(check_success, [200, 203])
    d.addCallback(treq.json_content)
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
        headers={'accept': ['application/json'],
                 'content-type': ['application/json']})
    d.addCallback(check_success, [200, 203])
    d.addCallback(treq.json_content)
    return d


def impersonate_user(auth_endpoint, impersonater_token, username, expire_in=10800):
    """
    Acquire an auth-token for a user via impersonation.

    :param str auth_endpoint: Identity API endpoint URL.
    :param str impersonater_token: Auth token that has the appropriate
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
        headers=headers(impersonater_token))
    d.addCallback(check_success, [200, 203])
    d.addCallback(treq.json_content)
    return d
