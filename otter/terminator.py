"""
Listen to user-access events and take appropriate action on the groups.
Based on https://one.rackspace.com/display/CUST/Access+Policy
"""

from __future__ import print_function

import json

from effect import Effect, parallel
from effect.do import do, do_return

from toolz.functoolz import compose
from toolz.curried import map

from txeffect import perform

from otter.cloud_client.cloudfeeds import Direction, read_entries
from otter.indexer import atom
from otter.models.intents import DeleteGroup, GetTenantGroups
from otter.util import zk


def terminator(dispatcher, log, zk_prev_path):
    d = perform(
        dispatcher,
        read_and_process("customer_access_events/events", zk_prev_path))
    return d.addErrback(log.err, "terminator-err", otter_service="terminator")


@do
def read_and_process(url, zk_prev_path):
    prev_params_json, stat = yield Effect(zk.GetNode(zk_prev_path))
    prev_params = json.loads(prev_params_json.decode("utf-8"))
    entries, prev_params = yield read_entries(url, prev_params,
                                              Direction.PREVIOUS)
    yield Effect(
        zk.UpdateNode(zk_prev_path, json.dumps(prev_params).encode("utf-8")))
    yield parallel(map(process_entry, entries))


class TenantStatus(object):
    """
    Status of tenant in access policy event
    """
    SUSPENDED = "SUSPENDED"
    FULL = "FULL"
    TERMINATED = "TERMINATED"


def enable_group(group):
    """
    Change any ERROR groups to ACTIVE and log about the update
    """


def suspend_group(group):
    """
    """


def delete_group(group):
    pass



def process_entry(entry):
    """
    Process the groups of tenant in the entry based on the status in the entry
    """
    tenant_id, status = extract_info(entry)
    process_group = {
        TenantStatus.FULL: enable_group,
        TenantStatus.SUSPENDED: suspend_group,
        TenantStatus.TERMINATED: delete_group
    }
    process_groups = compose(parallel, map(process_group[status]))
    return Effect(GetTenantGroups(tenant_id)).on(
        lambda groups: process_groups(groups) if groups else None)


def extract_info(entry):
    """
    Extract tenant_id and status from entry XML node
    """
    content = atom.xpath("./atom:content", entry)[0]
    ns = {"event": "http://docs.rackspace.com/core/event",
          "ap": "http://docs.rackspace.com/event/customer/access_policy"}
    tenant_id = atom.xpath("./event:event/@tenantId", content, ns)[0]
    status = atom.xpath("./event:event/ap:product/@status", content, ns)[0]
    return tenant_id, status
