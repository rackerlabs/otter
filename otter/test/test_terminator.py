"""
Tests for :mod:`otter.terminator`
"""

import json

import mock

from effect.testing import SequenceDispatcher, parallel_sequence

from twisted.trial.unittest import SynchronousTestCase

from otter import terminator as t
from otter.constants import ServiceType
from otter.cloud_client import TenantScope
from otter.cloud_client.cloudfeeds import Direction
from otter.indexer import atom
from otter.log.intents import BoundFields, Log, LogErr
from otter.models.intents import (
    DeleteGroup, GetTenantGroups, UpdateGroupErrorReasons,
    LoadAndUpdateGroupStatus)
from otter.models.interface import ScalingGroupStatus
from otter.util import zk
from otter.test.utils import (
    CheckFailure, const, conste, group_state, intent_func, nested_sequence,
    noop, perform_sequence)


class TerminatorTests(SynchronousTestCase):
    """
    Tests for :func:`terminator`
    """

    def setUp(self):
        self.patch(t, "read_and_process", intent_func("rap"))

    def test_success(self):
        """
        Calls :func:`read_and_process` wrapped in logging and tenanted context
        """
        seq = [
            (BoundFields(mock.ANY, dict(otter_service="terminator")),
             nested_sequence([
                 (TenantScope(mock.ANY, "tid"),
                  nested_sequence([
                      (("rap", "customer_access_policy/events", "/path"), noop)
                  ])
                 )
             ])
            )
        ]
        perform_sequence(seq, t.terminator("/path", "tid"))

    def test_error(self):
        """
        Any error occurring in :func:`read_and_process` is captured and logged
        with {"otter_service": "terminator"} field. Returns success.
        """
        seq = [
            (BoundFields(mock.ANY, dict(otter_service="terminator")),
             nested_sequence([
                 (TenantScope(mock.ANY, "tid"),
                  nested_sequence([
                      (("rap", "customer_access_policy/events", "/path"),
                       conste(ValueError("g")))
                  ])
                 ),
                 (LogErr(CheckFailure(ValueError), "terminator-err", {}), noop)
             ])
            )
        ]
        result = perform_sequence(seq, t.terminator("/path", "tid"))
        self.assertIsNone(result)


class ReadAndProcessTests(SynchronousTestCase):
    """
    Tests for :func:`read_and_process`
    """

    def test_success(self):
        """
        Read entries from last used "previous parameters" in ZK, updates the
        latest "previous parameters" back to ZK and process entries in parallel
        """
        self.patch(t, "read_entries", intent_func("re"))
        self.patch(t, "process_entry", intent_func("pe"))
        entries = ["element node1", "element node2"]
        params = {"a": "b"}
        params_json = json.dumps(params).encode("utf-8")
        new_params = {"b": "c"}
        new_params_json = json.dumps(new_params).encode("utf-8")
        seq = [
            (zk.GetNode("/prevpath"), const((params_json, "stat"))),
            (("re", ServiceType.CLOUD_FEEDS_CAP, "url", params,
              Direction.PREVIOUS),
             const((entries, new_params))),
            (zk.UpdateNode("/prevpath", new_params_json), noop),
            parallel_sequence([
                [(("pe", entries[0]), noop)], [(("pe", entries[1]), noop)]
            ])
        ]
        perform_sequence(seq, t.read_and_process("url", "/prevpath"))


class ProcessGroupTests(SynchronousTestCase):
    """
    Tests for group processing functions
    """

    def test_enable_group_suspended(self):
        """
        :func:`enable_group` changes group status to ACTIVE and logs about it
        if group's status is SUSPENDED
        """
        group = group_state("t1", "g1", status=ScalingGroupStatus.SUSPENDED)
        seq = [
            (LoadAndUpdateGroupStatus("t1", "g1", ScalingGroupStatus.ACTIVE),
             noop),
            (Log("group-status-active", dict(cloud_feed=True)), noop)
        ]
        perform_sequence(seq, t.enable_group(group))

    def test_enable_group(self):
        """
        :func:`enable_group` does nothing if group is not SUSPENDED
        """
        group = group_state("t1", "g1")
        perform_sequence([], t.enable_group(group))

    def test_suspend_group(self):
        """
        :func:`suspend_group` updates group status to SUSPENDED and logs to
        CF about it
        """
        group = group_state("t1", "g1")
        seq = [
            (LoadAndUpdateGroupStatus(
                "t1", "g1", ScalingGroupStatus.SUSPENDED),
             noop),
            (Log("group-status-suspended",
                 dict(cloud_feed=True, isError=True)),
             noop)
        ]
        perform_sequence(seq, t.suspend_group(group))

    def test_delete_group(self):
        """
        :func:`delete_group` deletes the group logs to CF about it
        """
        group = group_state("t1", "g1")
        seq = [
            (DeleteGroup("t1", "g1"), noop),
            (Log("group-status-terminated",
                 dict(cloud_feed=True, isError=True)), noop)
        ]
        perform_sequence(seq, t.delete_group(group))



entrystr = """
<entry xmlns="http://www.w3.org/2005/Atom">
  <atom:id xmlns:atom="http://www.w3.org/2005/Atom">urn:uuid:1a60f657-4e61-4c91-beaa-3ba31af9ebbb</atom:id>
  <atom:category xmlns:atom="http://www.w3.org/2005/Atom" term="tid:1009514"/>
  <atom:category xmlns:atom="http://www.w3.org/2005/Atom" term="rgn:GLOBAL"/>
  <atom:category xmlns:atom="http://www.w3.org/2005/Atom" term="dc:GLOBAL"/>
  <atom:category xmlns:atom="http://www.w3.org/2005/Atom" term="customerservice.access_policy.info"/>
  <atom:category xmlns:atom="http://www.w3.org/2005/Atom" term="type:customerservice.access_policy.info"/>
  <title type="text">CustomerService</title>
  <content type="application/xml">
    <event xmlns="http://docs.rackspace.com/core/event" xmlns:ns2="http://docs.rackspace.com/event/customer/access_policy" dataCenter="GLOBAL" environment="PROD" eventTime="2016-06-15T22:40:38.999Z" id="1a60f657-4e61-4c91-beaa-3ba31af9ebbb" region="GLOBAL" tenantId="{tenant_id}" type="INFO" version="2">
      <ns2:product previousEvent="" serviceCode="CustomerService" status="{status}" version="1"/>
    </event>
  </content>
  <link href="https://url/customer_access_policy/events/entries/urn:uuid:1a60f657-4e61-4c91-beaa-3ba31af9ebbb" rel="self"/>
  <updated>2016-06-15T22:40:39.215Z</updated>
  <published>2016-06-15T22:40:39.215Z</published>
</entry>
"""


class ProcessEntryTests(SynchronousTestCase):
    """
    Tests for :func:`process_entry`
    """
    def _test_proc_group(self, status, func_name):
        entry = atom.parse(entrystr.format(tenant_id="23", status=status))
        self.patch(t, func_name, intent_func("group_func"))
        groups = [group_state("t1", "g1"), group_state("t1", "g2")]

        def group_seq(g):
            boundfields = BoundFields(
                mock.ANY,
                dict(tenant_id=g.tenant_id, scaling_group_id=g.group_id))
            return (boundfields, nested_sequence([(("group_func", g), noop)]))

        seq = [
            (GetTenantGroups("23"), const(groups)),
            parallel_sequence([[group_seq(g)] for g in groups])
        ]
        perform_sequence(seq, t.process_entry(entry))

    def test_enable_group(self):
        """
        Entry with FULL status enables all the groups of the tenant
        """
        self._test_proc_group("FULL", "enable_group")

    def test_suspend_group(self):
        """
        Entry with SUSPENDED status disables all the groups of the tenant
        """
        self._test_proc_group("SUSPENDED", "suspend_group")

    def test_delete_group(self):
        """
        Entry with TERMINATED status deletes all the groups of the tenant
        """
        self._test_proc_group("TERMINATED", "delete_group")


class ExtractInfoTests(SynchronousTestCase):
    """
    Tests for :func:`extract_info`
    """
    def test_success(self):
        entry = atom.parse(entrystr.format(tenant_id="823645", status="SUSPENDED"))
        tenant_id, status = t.extract_info(entry)
        self.assertEqual(tenant_id, "823645")
        self.assertEqual(status, "SUSPENDED")
