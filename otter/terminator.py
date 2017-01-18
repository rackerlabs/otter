"""
Listen to user-access events and take appropriate action on the groups.
Based on https://one.rackspace.com/display/CUST/Access+Policy
"""

import json

import attr

from effect import Effect, parallel
from effect.do import do, do_return

from six import itervalues

from toolz.functoolz import compose, pipe
from toolz.curried import first, groupby, map

from otter.constants import ServiceType
from otter.cloud_client import TenantScope
from otter.cloud_client.cloudfeeds import Direction, read_entries
from otter.indexer import atom
from otter.log.cloudfeeds import cf_err, cf_msg
from otter.log.intents import err, err_exc_info, with_log
from otter.models.interface import ScalingGroupStatus
from otter.models.intents import (
    DeleteGroup, GetTenantGroupStates, ModifyGroupStateAttribute)
from otter.util import zk


def terminator(zk_prev_path, tenant_id):
    """
    Main entry point of this module. Basically performs and logs effect
    returned by :func:`read_and_process`

    :return: ``Effect``
    """
    rap_eff = read_and_process("customer_access_policy/events", zk_prev_path)
    tscope_eff = Effect(TenantScope(rap_eff, tenant_id))
    return with_log(tscope_eff.on(error=err_exc_info("terminator-err")),
                    otter_service="terminator")


@attr.s
class AtomEntry(object):
    """ Atom Entry containing tenant_id and status """
    tenant_id = attr.ib()
    status = attr.ib()


def extract_info(entry):
    """
    Extract tenant_id and status from entry XML node.

    :return: :obj:`AtomEntry`
    """
    content = atom.xpath("./atom:content", entry)[0]
    ns = {"event": "http://docs.rackspace.com/core/event",
          "ap": "http://docs.rackspace.com/event/customer/access_policy"}
    tenant_id = atom.xpath("./event:event/@tenantId", content, ns)[0]
    status = atom.xpath("./event:event/ap:product/@status", content, ns)[0]
    return AtomEntry(tenant_id, status)


@do
def read_and_process(url, zk_prev_path):
    """
    Read entries from last used "previous parameters" in ZK, process them
    and update the latest "previous parameters" back to ZK. It processes only
    latest event on a particular tenant.

    :return: ``Effect`` of list
    """
    prev_params_json, stat = yield Effect(zk.GetNode(zk_prev_path))
    prev_params = {}
    try:
        prev_params = json.loads(prev_params_json.decode("utf-8"))
    except Exception as e:
        yield err(None, "terminator-params-err", params_json=prev_params_json)
    entries, prev_params = yield read_entries(
        ServiceType.CLOUD_FEEDS_CAP, url, prev_params, Direction.PREVIOUS,
        log_msg_type="terminator-events-response")
    yield Effect(
        zk.UpdateNode(zk_prev_path, json.dumps(prev_params).encode("utf-8")))
    entries = pipe(entries,
                   map(extract_info),
                   groupby(lambda e: e.tenant_id),
                   itervalues,
                   map(first))
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

    :return: ``Effect`` of None
    """
    yield Effect(
        ModifyGroupStateAttribute(group.tenant_id, group.group_id,
                                  "suspended", False))
    yield cf_msg('terminator-group-active')


@do
def suspend_group(group):
    """
    SUSPEND the group and send CF log about it

    :return: ``Effect`` of None
    """
    yield Effect(
        ModifyGroupStateAttribute(group.tenant_id, group.group_id,
                                  "suspended", True))
    yield cf_err('terminator-group-suspended')


@do
def delete_group(group):
    """
    Delete the group and send CF log about it

    :return: ``Effect`` of None
    """
    yield Effect(DeleteGroup(group.tenant_id, group.group_id))
    yield cf_err("terminator-group-terminated")


def process_entry(entry):
    """
    Process the groups of tenant in the entry based on the status in the entry

    :return: ``Effect`` of list
    """
    process_group_mapping = {
        TenantStatus.FULL: enable_group,
        TenantStatus.SUSPENDED: suspend_group,
        TenantStatus.TERMINATED: delete_group
    }
    process_func = process_group_mapping[entry.status]

    def proc_with_log(group):
        return with_log(process_func(group), tenant_id=group.tenant_id,
                        scaling_group_id=group.group_id)

    process_groups = compose(parallel, map(proc_with_log))
    return Effect(GetTenantGroupStates(entry.tenant_id)).on(
        lambda groups: process_groups(groups) if groups else None)
