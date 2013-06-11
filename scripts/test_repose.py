#!/usr/bin/env python

"""
Basic test to make sure repose is set up mostly correctly to auth against an
identity server, and that webhooks do not need authorization
"""
from argparse import ArgumentParser
import json

import treq

from twisted.internet import defer, task

from otter.auth import authenticate_user
from otter.util.http import append_segments, headers, wrap_request_error


default_identity = "https://identity.api.rackspacecloud.com/v2.0/"


def request(url, purpose, method='GET', data=None, auth_token=None, expected=200):
    """
    Makes a treq GET request with the given method and URL.  For headers, takes
    the content type headers and possibly adds an auth token bit, if provided.

    Also checks that the status is the expected status, and wraps any timeouts
    to have a more useful error message.
    """
    def check_status(response):
        if response.code != expected:
            raise Exception(
                "{p} should result in a {e}.  Got {r} instead.".format(
                    p=purpose, e=expected, r=response.code))
        print '{} --> {}... ok!'.format(purpose, expected)
        return response

    def print_err_message(failure):
        print '{0} failed:\n{1!s}'.format(purpose, failure)
        return failure

    d = treq.request(method, url, headers=headers(auth_token), data=data)
    d.addErrback(wrap_request_error, url, data=auth_token)
    d.addCallbacks(check_status, print_err_message)
    return d


def test_webhook_doesnt_need_authentication(repose_endpoint, tenant_id, auth_token):
    """
    Trying to execute a webhook does not need any authentication.  Even if the
    webhook doesn't exist, a 202 is returned.  But a 4XX certainly shouldn't
    be returned.
    """
    url = append_segments(repose_endpoint, 'v1.0', 'execute', '1', tenant_id)
    return request(url, 'Executing a webhook without authentication',
                   method='POST', expected=202)


def test_list_groups_unauthenticated(repose_endpoint, tenant_id, auth_token):
    """
    Try to get groups, which returns with a 401 because it is unauthenticated
    """
    url = append_segments(repose_endpoint, 'v1.0', tenant_id, 'groups')
    return request(url, "Listing groups without authentication", expected=401)


def test_list_groups_authenticated(repose_endpoint, tenant_id, auth_token):
    """
    Try to get groups, which returns with a 200 because it is authenticated.
    """
    url = append_segments(repose_endpoint, 'v1.0', tenant_id, 'groups')
    return request(url, "Listing groups with authentication",
                   auth_token=auth_token)


def test_random_url_authenticated(repose_endpoint, tenant_id, auth_token):
    """
    Try to get some other URL at a different version, which returns with a 401
    because it is neither in the repose client-auth authenticated regex nor is
    it in the repose client-auth whitelist regex.
    """
    url = append_segments(repose_endpoint, 'v106', tenant_id, 'groups')
    return request(url, "Hitting an invalid url even with authentication",
                   auth_token=auth_token, expected=401)


def get_remaining_rate_limit(repose_endpoint, tenant_id, auth_token):
    """
    Get the remaining number of times a GET request can be made (since in these
    tests they are all GETs)
    """
    def get_limits(limits_dictionary):
        regexes = limits_dictionary['limits']['rate']
        rates = dict([(
            regex['regex'],
            dict([(rate['verb'], rate['remaining']) for rate in regex['limit']]))
            for regex in regexes])

        info = '\tRate info (by regex): {0}'.format(json.dumps(rates, indent=4))
        print '\n\t'.join(info.split('\n'))
        return rates

    url = append_segments(repose_endpoint, 'v1.0', tenant_id, 'limits')
    d = request(url, "Getting the rate limit info", auth_token=auth_token,
                expected=200)
    d.addCallback(treq.json_content)
    d.addCallback(get_limits)
    return d


@defer.inlineCallbacks
def run_tests(_, args):
    """
    Run the authenticated and unauthenticated tests.  Using inlinecallbacks
    because the logic is just easier to understand in this case.
    """
    blob = yield authenticate_user(args.identity, args.username, args.password)
    auth_token = blob['access']['token']['id'].encode('ascii')
    tenant_id = blob['access']['token']['tenant']['id'].encode('ascii')

    params = (args.repose, tenant_id, auth_token)

    old_rates = yield get_remaining_rate_limit(*params)

    yield defer.gatherResults([
        test_random_url_authenticated(*params),
        test_list_groups_authenticated(*params),
        test_list_groups_unauthenticated(*params),
        test_webhook_doesnt_need_authentication(*params)
    ], consumeErrors=True)

    new_rates = yield get_remaining_rate_limit(*params)

    for key in old_rates:
        if 'execute' in key:
            # because the execute rate limit doesn't seem to count down now
            continue
        else:
            # the non-execute webhook rate should have dropped by at least 2
            # (limit request, list groups authenticated request)
            assert old_rates[key]['ALL'] - new_rates[key]['ALL'] >= 2


def cli():
    """
    Run the script with parsed arguments
    """
    parser = ArgumentParser(description="Test repose setup.")
    parser.add_argument(
        'username', type=str,
        help='Username of user with credentials on identity service')

    parser.add_argument(
        'password', type=str,
        help='Password of the user with credentials on identity service')

    parser.add_argument(
        'repose', type=str, help='URL that points at repose.')

    parser.add_argument(
        '--identity-endpoint', type=str, dest='identity',
        help='URL of identity service: default {0}'.format(default_identity),
        default=default_identity)

    task.react(run_tests, [parser.parse_args()])


if __name__ == "__main__":
    cli()
