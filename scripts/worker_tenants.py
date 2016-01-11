#!/usr/bin/env python

"""
Script to print worker tenants. It gets all tenants from metrics and prints
tenants which are not in "convergence-tenants" config. Takes chef otter.json
as argument
"""

from __future__ import print_function

import json
import os
import sys

import treq

from twisted.internet import task
from twisted.internet.defer import inlineCallbacks

from otter.auth import generate_authenticator, public_endpoint_url
from otter.util.http import append_segments, check_success, headers


def get_tenant_ids(token, catalog):
    endpoint = public_endpoint_url(catalog, "cloudMetrics", "IAD")
    d = treq.get(
        append_segments(endpoint, "metrics", "search"),
        headers=headers(token), params={"query": "*.*.desired"})
    d.addCallback(check_success, [200])
    d.addCallback(treq.json_content)
    d.addCallback(lambda body: [item["metric"].split(".")[1] for item in body])
    return d


@inlineCallbacks
def main(reactor):
    conf = json.load(open(sys.argv[1]))
    conf = conf["default_attributes"]["otter"]["config"]
    conf["identity"]["strategy"] = "single_tenant"
    conf["identity"]["username"] = os.environ["OTTERPROD_UNAME"]
    conf["identity"]["password"] = os.environ["OTTERPROD_PWD"]
    authenticator = generate_authenticator(reactor, conf["identity"])
    token, catalog = yield authenticator.authenticate_tenant("764771")
    all_tenants = set((yield get_tenant_ids(token, catalog)))
    worker_tenants = all_tenants - set(conf["convergence-tenants"])
    print(*worker_tenants, sep='\n')


if __name__ == '__main__':
    task.react(main, ())
