""" CQL Batch wrapper"""

from silverberg.client import ConsistencyLevel

from otter.util.deferredutils import timeout_deferred


class Batch(object):
    """ CQL Batch wrapper"""
    def __init__(self, statements, params, consistency=ConsistencyLevel.ONE,
                 timestamp=None):
        self.statements = statements
        self.params = params
        self.consistency = consistency
        self.timestamp = timestamp

    def _generate(self):
        str = 'BEGIN BATCH '
        if self.timestamp is not None:
            str += 'USING TIMESTAMP {} '.format(self.timestamp)
        str += ' '.join(self.statements)
        str += ' APPLY BATCH;'
        return str

    def execute(self, client):
        """
        Execute the CQL batch against the given client object
        """
        return client.execute(self._generate(), self.params, self.consistency)


# TODO: This should ideally goto silverberg but is here due to `timeout_deferred`
# implementation. It should be coming out in Twisted itself.
# See http://twistedmatrix.com/trac/changeset/42627
class TimingOutCQLClient(object):
    """
    A CQLClient implementation that supports timing out after some interval

    :param IReactorTime reactor: A IReactorTime provider
    :param CQLClient client: An implementation of CQLClient
    :param int timeout: Seconds after which query will timeout
    """

    def __init__(self, reactor, client, timeout=30):
        self._reactor = reactor
        self._client = client
        self._timeout = timeout

    def execute(self, *args, **kwargs):
        """
        See :py:func:`silverberg.client.CQLClient.execute`
        """
        d = self._client.execute(*args, **kwargs)
        timeout_deferred(d, self._timeout, self._reactor, 'CQL query')
        return d
