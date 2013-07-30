"""
Tests for the Audit Log.
"""

import mock
import uuid

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed

from zope.interface.verify import verifyObject

from silverberg.client import CQLClient, ConsistencyLevel

from otter.audit_log.models import CassandraAuditLog, IAuditLog

ts1 = uuid.UUID('df3376c7-d86b-11e2-b92c-1040f3e9b720')
ts2 = uuid.UUID('49825240-de87-11e2-8651-406c8f25a009')


class CassandraAuditLogTests(TestCase):
    """
    Test cassandra backed audit logs.
    """
    def setUp(self):
        """
        Set up a mock CQLClient.
        """
        self.client = mock.Mock(CQLClient)
        self.audit_log = CassandraAuditLog(self.client)

    def test_verifyObject(self):
        """
        Verify the API provided CassandraAuditLog matches the
        defined interface.
        """
        verifyObject(IAuditLog, self.audit_log)

    @mock.patch('otter.audit_log.models.uuid.uuid1')
    def test_add_log_entry(self, uuid1):
        """
        add_log_entry executes an INSERT with the tenantId, timestamp, and
        JSON encoded data.
        """

        uuid1.return_value = ts1

        self.audit_log.add_log_entry('111111', {})

        self.client.execute.assert_called_once_with(
            ('INSERT INTO audit_log ("tenantId", "logTime", "logEvent") '
             'VALUES (:tenantId, :logTime, :logEvent);'),
            {'tenantId': '111111', 'logTime': ts1,
             'logEvent': '{}'},
            ConsistencyLevel.ONE)

    def test_entries_for_tenant(self):
        """
        entries_for_tenant returns all log entries.
        """
        self.client.execute.return_value = succeed([
            {'tenantId': '111111', 'logTime': ts1, 'logEvent': '{"stuff": 1}'},
            {'tenantId': '111111', 'logTime': ts2, 'logEvent': '{"stuff": 2}'}
        ])

        d = self.audit_log.entries_for_tenant('111111')
        result = self.successResultOf(d)
        self.assertEqual(result, [{'stuff': 1}, {'stuff': 2}])

        self.client.execute.assert_called_once_with(
            ('SELECT "logEvent" FROM audit_log WHERE "tenantId" = :tenantId '
             'ORDER BY "logTime";'),
            {'tenantId': '111111'},
            ConsistencyLevel.ONE)
