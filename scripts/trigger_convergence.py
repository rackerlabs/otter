"""
Trigger convergence on all or specific tenants/groups. Requires otter type
config file containing region, identity and cassandra info

Examples:
`python trigger_convergence -c config.json -g "tenantid:groupId"`
will trigger convergence on given group(s)
`python trigger_convergence -c config.json`
will trigger convergence on all groups got from cassandra
"""

import json
import sys
from argparse import ArgumentParser

import treq

from twisted.internet import task
from twisted.internet.defer import (
    DeferredSemaphore, gatherResults, inlineCallbacks)

from otter.auth import generate_authenticator, public_endpoint_url
from otter.metrics import connect_cass_servers
from otter.models.cass import CassScalingGroupCollection
from otter.util.http import append_segments, headers


@inlineCallbacks
def trigger_convergence(authenticator, region, group):
    token, catalog = yield authenticator.authenticate_tenant(group["tenantId"])
    endpoint = public_endpoint_url(catalog, "autoscale", region)
    resp = yield treq.post(
        append_segments(endpoint, "groups", group["groupId"], "converge"),
        headers=headers(token), data="")
    if resp.code != 204:
        raise ValueError("bad code", resp.code)


def trigger_convergence_groups(authenticator, region, groups,
                               concurrency_limit):
    """
    Trigger convergence on given groups
    """
    sem = DeferredSemaphore(concurrency_limit)
    return gatherResults(
        [sem.run(trigger_convergence, authenticator, region, group)
         for group in groups],
        consumeErrors=True)


@inlineCallbacks
def main(reactor):
    parser = ArgumentParser(
        description="Trigger convergence on all/some groups")
    parser.add_argument("-c", dest="config", required=True,
                        help="Config file containing identity and cassandra info")
    parser.add_argument(
        "-g", nargs="+", dest="group",
        help=("Group to trigger. Should be in tenantId:groupId form. "
              "If not provided convergence will be triggerred on all groups "
              "in CASS"))
    parser.add_argument("-l", dest="limit", help="Concurrency limit", type=int,
                        default=10)

    parsed = parser.parse_args()
    conf = json.load(open(parsed.config))

    cass_client = connect_cass_servers(reactor, conf["cassandra"])
    authenticator = generate_authenticator(reactor, conf["identity"])
    store = CassScalingGroupCollection(cass_client, reactor, 1000)
    if parsed.group:
        groups = [g.split(":") for g in parsed.group]
        groups = [{"tenantId": tid, "groupId": gid} for tid, gid in groups]
    else:
        groups = yield store.get_all_groups()

    yield trigger_convergence_groups(authenticator, conf["region"], groups,
                                     parsed.limit)
    yield cass_client.disconnect()


if __name__ == '__main__':
    task.react(main, ())
