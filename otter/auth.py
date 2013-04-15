"""
Functions for resolving authentication information.
"""

import json
import treq


def authenticate_tenant(tenant_id):
    """
    Authenticate as the desired tenant.

    :params tenant_id: id of the tenant to authenticate as
    :returns: Deferred that fires with a 2-tuple of auth token and service catalog.
    """

    raise NotImplementedError()


DEFAULT_INTERNAL_IDENTITY_API_URL = 'https://identity-internal.api.rackspacecloud.com/v2.0'
DEFAULT_IDENTITY_API_URL = 'https://identity.api.rackspacecloud.com/v2.0'


class ImpersonationAuthenticator(object):
    def __init__(self, service_user, service_api_key,
                 identity_url=None, internal_url=None):
        self._service_user = service_user
        self._service_api_key = service_api_key
        self._identity_url = identity_url or DEFAULT_IDENTITY_API_URL
        self._internal_url = internal_url or DEFAULT_INTERNAL_IDENTITY_API_URL

    def token_for_tenant(self, tenant_id):
        """
        :param tenant_id: The keystone tenant_id we wish to impersonate.
        :returns: a deferred that fires with a 2-tuple of auth-token and
            service catalog.
        """
        d = authenticate_user(self._identity_url,
                              self._service_user,
                              self._service_api_key)
        d.addCallback(extract_token)

        def find_user(impersonator_token):
            return lookup_user(
                self._internal_url,
                impersonator_token,
                tenant_id).addCallback(
                    lambda users: (impersonator_token, users['users'][0]['username']))

        d.addCallback(find_user)

        def impersonate((impersonator_token, user)):
            iud = impersonate_user(self._internal_url,
                                   impersonator_token,
                                   user)
            iud.addCallback(extract_token)
            iud.addCallback(lambda token: (impersonator_token, token))
            return iud

        d.addCallback(impersonate)

        def endpoints((impersonator_token, token)):
            scd = service_catalog(self._internal_url, impersonator_token, token)
            scd.addCallback(lambda catalog: (token, catalog.get('endpoints', [])))
            return scd

        d.addCallback(endpoints)

        return d


def extract_token(resp):
    return resp['access']['token']['id'].encode('ascii')


def _printf(failure):
    print failure.value


def _print(r):
    import pprint
    pprint.pprint(r)
    return r


def service_catalog(auth_endpoint, impersonator_token, auth_token):
    d = treq.get(auth_endpoint + '/tokens/' + auth_token + '/endpoints',
                 headers={'accept': ['application/json'],
                          'content-type': ['application/json'],
                          'x-auth-token': [impersonator_token]})

    d.addCallback(treq.json_content)
    return d


def lookup_user(auth_endpoint, auth_token, tenant_id):
    d = treq.get(
        auth_endpoint + '/tenants/' + str(tenant_id) + '/users',
        headers={'accept': ['application/json'],
                 'content-type': ['application/json'],
                 'x-auth-token': [auth_token]})

    d.addCallback(treq.json_content)
    return d


def authenticate_user(auth_endpoint, username, password):
    d = treq.post(
        auth_endpoint + '/tokens',
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
    d.addCallback(treq.json_content)
    return d


def impersonate_user(auth_endpoint, impersonater_token, username, expires_in=10800):
    d = treq.post(
        auth_endpoint + '/RAX-AUTH/impersonation-tokens',
        json.dumps({
            "RAX-AUTH:impersonation": {
                "user": {"username": username},
                "expire-in-seconds": expires_in
            }
        }),
        headers={'accept': ['application/json'],
                 'content-type': ['application/json'],
                 'X-Auth-Token': [impersonater_token]})
    d.addCallback(treq.json_content)
    return d


if __name__ == '__main__':
    import sys

    from twisted.internet.task import react
    from twisted.internet.defer import inlineCallbacks

    @inlineCallbacks
    def main(reactor, username, api_key):
        staging = 'https://staging.identity.api.rackspacecloud.com/v2.0'
        ia = ImpersonationAuthenticator(username, api_key, identity_url=staging,
                                        internal_url=staging)

        r = yield ia.token_for_tenant('5821004')
        _print(r)

    react(main, sys.argv[1:])
