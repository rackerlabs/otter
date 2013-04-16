"""
Basic test to make sure repose is set up mostly correctly to auth against an
identity server, and that webhooks do not need authorization
"""
from argparse import ArgumentParser
import json

import treq

from twisted.internet import defer, task

from otter.util.http import append_segments
from otter.util.deferredutils import unwrap_first_error

default_identity = "https://staging.identity.api.rackspacecloud.com/v2.0/"

content_type = {'content-type': ['application/json'],
                'accept': ['application/json']}


def test_webhook_doesnt_need_authentication(repose_endpoint):
    """
    Trying to execute a webhook does not need any authentication.  Even if the
    webhook doesn't exist, a 202 is returned.  But a 4XX certainly shouldn't
    be returned.
    """
    d = treq.post(
        append_segments(repose_endpoint, 'v1.0', 'execute', '1', 'random'),
        headers=content_type)

    def check_202(response):
        if response.code != 202:
            raise Exception(
                ("Executing a webhook without authentication should result "
                 "in a 202.  Got {0} instead.").format(response.code))

    return d.addCallback(check_202)


def test_list_groups_authenticated(repose_endpoint, tenant_id, auth_headers):
    """
    Try to get groups, which returns with a 200 because it is authenticated.
    """
    d = treq.get(append_segments(repose_endpoint, 'v1.0', tenant_id, 'groups'),
                 headers=auth_headers)

    def check_200(response):
        if response.code != 200:
            raise Exception(
                ("Listing groups with authentication should result in a 200."
                 "Got {0} instead.").format(response.code))

    return d.addCallback(check_200)


def test_random_url_not_authenticated(repose_endpoint, tenant_id, auth_headers):
    """
    Try to get some other URL at a different version, which returns with a 401
    because it is neither in the repose client-auth authenticated regex nor is
    it in the repose client-auth whitelist regex.
    """
    d = treq.get(append_segments(repose_endpoint, 'v10.6', tenant_id, 'groups'),
                 headers=auth_headers)

    def check_401(response):
        if response.code != 401:
            raise Exception(
                ("Hitting an invalid URL should result in a 401."
                 "Got {0} instead.").format(response.code))

    return d.addCallback(check_401)


def get_token_and_tenant(identity_endpoint, username, api_key):
    """
    Hit auth manually to get a valid auth token with which to test repose
    """
    data = {
        "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
                "username": username,
                "apiKey": api_key
            }
        }
    }

    d = treq.post(append_segments(identity_endpoint, 'tokens'),
                  headers=content_type, data=json.dumps(data))

    def extract_token_and_tenant(response):
        if response.code == 200:
            contents = treq.content(response)
            contents.addCallback(json.loads)
            contents.addCallback(lambda blob: (
                blob['access']['token']['id'].encode('ascii'),
                blob['access']['token']['tenant']['id'].encode('ascii')))
            return contents
        raise Exception('User {0} unauthorized.'.format(username))

    return d.addCallback(extract_token_and_tenant)


def run_authorized_tests(token_and_tenant, args):
    """
    Run the tests that require the user to be authenticated
    """
    auth_token, tenant_id = token_and_tenant
    headers = content_type.copy()
    headers['x-auth-token'] = [auth_token]

    return defer.gatherResults(
        # [test_random_url_not_authenticated(args.repose, tenant_id, headers),
        [test_list_groups_authenticated(args.repose, tenant_id, headers)],
        consumeErrors=True)


def run_all_tests(_, args):
    """
    Run the authenticated and unauthenticated tests
    """
    d = defer.gatherResults(
        [get_token_and_tenant(args.identity, args.username, args.apikey).addCallback(
            run_authorized_tests, args),
         test_webhook_doesnt_need_authentication(args.repose)])
    d.addErrback(unwrap_first_error)  # get the actual error returned
    return d


def cli():
    """
    Run the script with parsed arguments
    """
    parser = ArgumentParser(description="Test repose setup.")
    parser.add_argument(
        'username', type=str,
        help='Username of user with credentials on identity service')

    parser.add_argument(
        'apikey', type=str,
        help='API key of user with credentials on identity service')

    parser.add_argument(
        'repose', type=str, help='URL that points at repose.')

    parser.add_argument(
        '--identity-endpoint', type=str, dest='identity',
        help='URL of identity service: default {0}'.format(default_identity),
        default=default_identity)

    task.react(run_all_tests, [parser.parse_args()])


cli()
