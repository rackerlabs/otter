""" CQL Batch wrapper test """
from twisted.trial.unittest import SynchronousTestCase
import mock
from twisted.internet import defer
from twisted.internet.task import Clock

from silverberg.client import ConsistencyLevel

from otter.util.cqlbatch import Batch, TimingOutCQLClient
from otter.util.deferredutils import TimedOutError


class CqlBatchTestCase(SynchronousTestCase):
    """
    CQL Batch wrapper test case
    """

    def setUp(self):
        """
        setup
        """
        self.connection = mock.MagicMock()
        self.connection.execute.return_value = defer.succeed(None)

    def test_batch(self):
        """
        Test a simple batch
        """
        batch = Batch(['INSERT * INTO BLAH', 'INSERT * INTO BLOO'], {})
        d = batch.execute(self.connection)
        self.successResultOf(d)
        expected = 'BEGIN BATCH INSERT * INTO BLAH'
        expected += ' INSERT * INTO BLOO APPLY BATCH;'
        self.connection.execute.assert_called_once_with(expected, {},
                                                        ConsistencyLevel.ONE)

    def test_batch_param(self):
        """
        Test a simple batch with params
        """
        params = {"blah": "ff"}
        batch = Batch(['INSERT :blah INTO BLAH', 'INSERT * INTO BLOO'],
                      params)
        d = batch.execute(self.connection)
        self.successResultOf(d)
        expected = 'BEGIN BATCH INSERT :blah INTO BLAH'
        expected += ' INSERT * INTO BLOO APPLY BATCH;'
        self.connection.execute.assert_called_once_with(expected, params,
                                                        ConsistencyLevel.ONE)

    def test_batch_ts(self):
        """
        Test a simple batch with timestamp set
        """
        batch = Batch(['INSERT * INTO BLAH'], {}, timestamp=123)
        d = batch.execute(self.connection)
        self.successResultOf(d)
        expected = 'BEGIN BATCH USING TIMESTAMP 123'
        expected += ' INSERT * INTO BLAH APPLY BATCH;'
        self.connection.execute.assert_called_once_with(expected, {},
                                                        ConsistencyLevel.ONE)

    def test_batch_consistency(self):
        """
        Test a simple batch with consistency set
        """
        batch = Batch(['INSERT * INTO BLAH'], {},
                      consistency=ConsistencyLevel.QUORUM)
        d = batch.execute(self.connection)
        self.successResultOf(d)
        expected = 'BEGIN BATCH'
        expected += ' INSERT * INTO BLAH APPLY BATCH;'
        self.connection.execute.assert_called_once_with(
            expected, {}, ConsistencyLevel.QUORUM)


class TimingOutCQLClientTests(SynchronousTestCase):
    """
    Tests for `:py:class:TimingOutCQLClient`
    """

    def setUp(self):
        """
        Sample client and clock
        """
        self.client = mock.Mock(spec=['execute'])
        self.clock = Clock()
        self.tclient = TimingOutCQLClient(self.clock, self.client, 10)

    def test_execute(self):
        """
        Execute is delgated to the client
        """
        self.client.execute.return_value = defer.succeed(5)
        d = self.tclient.execute(2, 3, a=4)
        self.assertEqual(self.successResultOf(d), 5)
        self.client.execute.assert_called_once_with(2, 3, a=4)

    def test_times_out(self):
        """
        Execute times out after given time
        """
        self.client.execute.return_value = defer.Deferred()
        d = self.tclient.execute(2, 3)
        self.assertNoResult(d)
        self.clock.advance(10)
        self.failureResultOf(d, TimedOutError)
