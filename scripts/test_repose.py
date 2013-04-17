#!/usr/bin/env python

"""
Basic test to make sure repose is set up mostly correctly to auth against an
identity server, and that webhooks do not need authorization
"""
from argparse import ArgumentParser
import json
from urlparse import urlparse

import treq

from twisted.internet import defer, error, task

from otter.util.http import append_segments
from otter.util.deferredutils import unwrap_first_error


default_identity = "https://staging.identity.api.rackspacecloud.com/v2.0/"

content_type = {'content-type': ['application/json'],
                'accept': ['application/json']}


def wrap_connection_timeout(failure, url):
    """
    Connection timeouts aren't useful becuase they don't contain the netloc
    that is timing out, so wrap the error.
    """
    if failure.check(error.TimeoutError):
        raise Exception('Timed out trying to hit {0}'.format(
            urlparse(url).netloc))
    return failure


def check_status_cb(purpose, expected=200):
    """
    Get a callback that can be used to check the status of a response and
    print a nice error message.
    """
    def check_status(response):
        if response.code != expected:
            raise Exception(
                "{p} should result in a {e}.  Got {r} instead.".format(
                    p=purpose, e=expected, r=response.code))
    return check_status


def request(url, method='GET', data=None, auth_token=None):
    """
    Makes a treq GET request with the given method and URL.  For headers, takes
    the content type headers and possibly adds an auth token bit, if provided.

    Also checks that the status is the expected status, and wraps any timeouts
    to have a more useful error message.
    """
    if auth_token is None:
        headers = content_type
    else:
        headers = content_type.copy()
        headers['x-auth-token'] = [auth_token]

    d = treq.request(method, url, headers=headers, data=data)
    d.addErrback(wrap_connection_timeout, url)
    return d


def test_webhook_doesnt_need_authentication(repose_endpoint):
    """
    Trying to execute a webhook does not need any authentication.  Even if the
    webhook doesn't exist, a 202 is returned.  But a 4XX certainly shouldn't
    be returned.
    """
    url = append_segments(repose_endpoint, 'v1.0', 'execute', '1', 'random')
    d = request(url, method='POST')
    d.addCallback(check_status_cb('Executing a webhook without authentication',
                                  expected=202))
    return d


def test_list_groups_unauthenticated(repose_endpoint, tenant_id):
    """
    Try to get groups, which returns with a 401 because it is unauthenticated
    """
    url = append_segments(repose_endpoint, 'v1.0', tenant_id, 'groups')
    d = request(url)
    d.addCallback(check_status_cb("Listing groups with authentication",
                                  expected=401))
    return d


def test_list_groups_authenticated(repose_endpoint, tenant_id, auth_token):
    """
    Try to get groups, which returns with a 200 because it is authenticated.
    """
    url = append_segments(repose_endpoint, 'v1.0', tenant_id, 'groups')
    d = request(url, auth_token=auth_token)
    d.addCallback(check_status_cb("Listing groups with authentication"))
    return d


def test_random_url_authenticated(repose_endpoint, tenant_id, auth_token):
    """
    Try to get some other URL at a different version, which returns with a 401
    because it is neither in the repose client-auth authenticated regex nor is
    it in the repose client-auth whitelist regex.
    """
    url = append_segments(repose_endpoint, 'v10.6', tenant_id, 'groups')
    d = request(url, auth_token=auth_token)
    d.addCallback(check_status_cb("Hitting an invalid url even with authentication",
                                  expected=401))
    return d


def get_user_info(identity_endpoint, username, api_key):
    """
    Hit auth manually to get a valid auth token (and the tenant ID) with which
    to test repose
    """
    data = {
        "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
                "username": username,
                "apiKey": api_key
            }
        }
    }

    url = append_segments(identity_endpoint, 'tokens')
    d = request(url, method='POST', data=json.dumps(data))

    def extract_token_and_tenant(response):
        if response.code == 200:
            contents = treq.content(response)
            contents.addCallback(json.loads)
            contents.addCallback(lambda blob: (
                blob['access']['token']['id'].encode('ascii'),
                blob['access']['token']['tenant']['id'].encode('ascii')))
            return contents
        raise Exception('User {0} unauthorized.'.format(username))

    d.addCallback(extract_token_and_tenant)
    return d


def run_tests(_, args):
    """
    Run the authenticated and unauthenticated tests.
    """

    def _do_tests(token_and_tenant):
        """
        Run the tests that require the user to be authenticated
        """
        auth_token, tenant_id = token_and_tenant

        return defer.gatherResults(
            [test_random_url_authenticated(args.repose, tenant_id, auth_token),
             test_list_groups_authenticated(args.repose, tenant_id, auth_token),
             test_list_groups_unauthenticated(args.repose, tenant_id),
             test_webhook_doesnt_need_authentication(args.repose)],
            consumeErrors=True)

    d = get_user_info(args.identity, args.username, args.apikey)
    d.addCallback(_do_tests)
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

    task.react(run_tests, [parser.parse_args()])


cli()
