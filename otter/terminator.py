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
from otter.log.cloudfeeds import cf_err, cf_msg
from otter.log.intents import err_exc_info, with_log
from otter.models.interface import ScalingGroupStatus
from otter.models.intents import (
    DeleteGroup, GetTenantGroups, UpdateGroupErrorReasons, UpdateGroupStatus)
from otter.util import zk


def terminator(dispatcher, zk_prev_path):
    """
    Main entry point of this module. Basically performs and logs effect
    returned by :func:`read_and_process`

    :return: ``Deferred`` of None
    """
    eff = with_log(
        read_and_process("customer_access_policy/events", zk_prev_path).on(
            error=err_exc_info("terminator-err")),
        otter_service="terminator")
    return perform(dispatcher, eff)


@do
def read_and_process(url, zk_prev_path):
    """
    Read entries from last used "previous parameters" in ZK, process them
    and update the latest "previous parameters" back to ZK

    :return: ``Effect``
    """
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


@do
def enable_group(group):
    """
    Change any SUSPENDED groups to ACTIVE and log about the update

    :return: ``Effect``
    """
    if group.status == ScalingGroupStatus.SUSPENDED:
        yield Effect(UpdateGroupStatus(scaling_group=group,
                                       status=ScalingGroupStatus.ACTIVE))
        yield cf_msg('group-status-active')


@do
def suspend_group(group):
    """
    SUSPEND the group and send CF log about it

    :return: ``Effect``
    """
    yield Effect(UpdateGroupStatus(scaling_group=group,
                                   status=ScalingGroupStatus.SUSPENDED))
    yield cf_err('group-status-suspended')


@do
def delete_group(group):
    """
    Delete the group and send CF log about it

    :return: ``Effect``
    """
    yield Effect(DeleteGroup(group.tenant_id, group.group_id))
    yield cf_err("group-status-terminated")


def process_entry(entry):
    """
    Process the groups of tenant in the entry based on the status in the entry

    :return: ``Effect``
    """
    tenant_id, status = extract_info(entry)
    process_group_mapping = {
        TenantStatus.FULL: enable_group,
        TenantStatus.SUSPENDED: suspend_group,
        TenantStatus.TERMINATED: delete_group
    }
    process_func = process_group_mapping[status]

    def proc_with_log(group):
        return with_log(process_func(group), tenant_id=group.tenant_id,
                        scaling_group_id=group.group_id)

    process_groups = compose(parallel, map(proc_with_log))
    return Effect(GetTenantGroups(tenant_id)).on(
        lambda groups: process_groups(groups) if groups else None)


def extract_info(entry):
    """
    Extract tenant_id and status from entry XML node.

    :return: (tenant_id, status) tuple
    """
    content = atom.xpath("./atom:content", entry)[0]
    ns = {"event": "http://docs.rackspace.com/core/event",
          "ap": "http://docs.rackspace.com/event/customer/access_policy"}
    tenant_id = atom.xpath("./event:event/@tenantId", content, ns)[0]
    status = atom.xpath("./event:event/ap:product/@status", content, ns)[0]
    return tenant_id, status
