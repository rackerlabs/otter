"""
The Audit Log is a record of all actions performed on behalf of a given tenant.

It is an immutable time-ordered log of events.
"""
import json
import uuid

from zope.interface import Interface, implementer
from silverberg.client import ConsistencyLevel


class IAuditLog(Interface):
    """
    An audit log is a time ordered tenanted log of events.
    """
    def add_log_entry(tenant_id, event_dict):
        """
        Add an event to the audit log for ``tenant_id``.

        :param tenant_id: Tenant ID of the user affected by this event.
        :param dict event_dict: The event to add to the audit log.

        :return: A deferred that fires with ``None`` when the event is added.
        """

    def entries_for_tenant(tenant_id):
        """
        Return the audit log entries for a tenant.

        TODO: Pagination.

        :param tenant_id: Tenant ID of the audit log to view.

        :return: a deferred that fires with an iterable of entries.
        """


@implementer(IAuditLog)
class CassandraAuditLog(object):
    """
    A Cassandra backed implementation of IAuditLog.  It stores log events as
    JSON blobs.
    """
    def __init__(self, client):
        """
        :param CQLClient client: A CQLClient (or compatible) instance to be
            used for executing queries.
        """
        self._client = client

    def add_log_entry(self, tenant_id, event):
        """
        see :meth:`otter.audit_log.models.IAuditLog.add_log_entry`
        """
        query = ('INSERT INTO audit_log ("tenantId", "logTime", "logEvent") '
                 'VALUES (:tenantId, :logTime, :logEvent);')

        return self._client.execute(query,
                                    {"logTime": uuid.uuid1(),
                                     "tenantId": tenant_id,
                                     "logEvent": json.dumps(event)},
                                    ConsistencyLevel.ONE)

    def entries_for_tenant(self, tenant_id):
        """
        see :meth:`otter.audit_log.models.IAuditLog.entries_for_tenant`
        """
        query = ('SELECT "logEvent" '
                 'FROM audit_log '
                 'WHERE "tenantId" = :tenantId '
                 'ORDER BY "logTime";')

        def decode_results(rows):
            return [json.loads(row['logEvent']) for row in rows]

        d = self._client.execute(query, {"tenantId": tenant_id}, ConsistencyLevel.ONE)
        d.addCallback(decode_results)
        return d
