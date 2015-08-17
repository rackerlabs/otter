"""Tests for otter.util.zkpartitioner"""

from kazoo.recipe.partitioner import PartitionState

import mock

from twisted.internet.defer import Deferred
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.test.utils import mock_log
from otter.util.zkpartitioner import Partitioner


class PartitionerTests(SynchronousTestCase):
    """Tests for :obj:`Partitioner`."""

    def setUp(self):
        self.clock = Clock()
        self.kz_client = mock.Mock(spec=['SetPartitioner'])
        self.kz_partitioner = mock.MagicMock(
            allocating=False,
            release=False,
            failed=False,
            acquired=False)
        self.kz_client.SetPartitioner.return_value = self.kz_partitioner
        self.path = '/the-part-path'
        self.buckets = range(5)
        self.log = mock_log()
        self.time_boundary = 30
        self.buckets_received = []
        self.partitioner = Partitioner(
            self.kz_client, 10, self.path, self.buckets, self.time_boundary,
            self.log, self.buckets_received.append, clock=self.clock)

    def test_allocating(self):
        """When state is ``allocating``, nothing happens."""
        self.kz_partitioner.allocating = True
        self.partitioner.startService()
        self.log.msg.assert_called_with('Partition allocating',
                                        otter_msg_type='partition-allocating')
        self.assertEqual(self.buckets_received, [])

    def test_release(self):
        """
        When state is ``release``, the :obj:`SetPartitioner`'s ``release_set``
        method is called.
        """
        self.kz_partitioner.release = True
        self.partitioner.startService()
        self.log.msg.assert_called_with('Partition changed. Repartitioning',
                                        otter_msg_type='partition-released')
        self.kz_partitioner.release_set.assert_called_once_with()
        self.assertEqual(self.buckets_received, [])

    def test_failed(self):
        """When state is ``failed``, a new partitioner is created."""
        self.kz_partitioner.allocating = True
        self.partitioner.startService()

        self.kz_partitioner.allocating = False
        self.kz_partitioner.failed = True
        # expect a new SetPartitioner to be created
        new_kz_partition = object()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.clock.advance(10)

        self.log.msg.assert_called_with('Partition failed. Starting new',
                                        otter_msg_type='partition-failed')
        # Called once when starting and now again when partition failed
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.path,
                                    set=self.buckets,
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.partitioner.partitioner, new_kz_partition)
        self.assertEqual(self.buckets_received, [])

    def test_invalid_state(self):
        """
        When none of the expected states are True, the ``finish`` method is
        called on the partitioner and a new partitioner is created.
        """
        self.kz_partitioner.allocating = True
        self.partitioner.startService()
        self.kz_partitioner.allocating = False
        self.kz_partitioner.state = 'bad'

        # expect a new SetPartitioner to be created
        new_kz_partition = object()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.clock.advance(10)

        self.log.err.assert_called_with(
            'Unknown state bad. This cannot happen. Starting new',
            otter_msg_type='partition-invalid-state')
        self.kz_partitioner.finish.assert_called_once_with()

        # Called once when starting and now again when got bad state
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.path,
                                    set=self.buckets,
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.partitioner.partitioner, new_kz_partition)
        self.assertEqual(self.buckets_received, [])

    def test_acquired(self):
        """When state is acquired, our callback is invoked with the buckets."""
        self.kz_partitioner.acquired = True
        self.kz_partitioner.__iter__.return_value = iter([2, 3])
        self.partitioner.startService()
        self.log.msg.assert_called_once_with(
            'Got buckets {buckets}',
            buckets=[2, 3], old_buckets=[], path=self.path,
            otter_msg_type='partition-acquired')
        self.assertEqual(self.buckets_received, [[2, 3]])

    def test_repeat(self):
        """
        buckets are received every iteration that the partitioner is acquired.
        """
        self.kz_partitioner.acquired = True
        self.kz_partitioner.__iter__.return_value = [2, 3]
        self.partitioner.startService()
        self.log.msg.assert_called_once_with(
            'Got buckets {buckets}',
            buckets=[2, 3], old_buckets=[], path=self.path,
            otter_msg_type='partition-acquired')
        self.clock.advance(10)
        self.clock.advance(10)
        self.assertEqual(self.buckets_received, [[2, 3], [2, 3], [2, 3]])

    def test_got_buckets_return(self):
        """
        `got_buckets` return value is propogated to timerservice that ensures
        that the service stops after returned deferred is fired
        """
        self.kz_partitioner.acquired = True
        self.kz_partitioner.__iter__.return_value = [2, 3]
        self.buckets_got = None
        d = Deferred()

        def got_buckets(_buckets):
            self.buckets_got = _buckets
            return d

        partitioner = Partitioner(
            self.kz_client, 10, self.path, self.buckets, self.time_boundary,
            self.log, got_buckets, clock=self.clock)
        partitioner.startService()
        self.log.msg.assert_called_once_with(
            'Got buckets {buckets}',
            buckets=[2, 3], old_buckets=[], path=self.path,
            otter_msg_type='partition-acquired')
        self.assertEqual(self.buckets_got, [2, 3])
        self.clock.advance(10)
        # Stopping service does not complete even after advancing clock
        # since got_buckets deferred has not fired yet
        sd = partitioner.stopService()
        self.assertNoResult(sd)
        # Service stops after deferred is fired
        d.callback(None)
        self.successResultOf(sd)

    def test_no_log_spam(self):
        """Bucket changes are not logged when the buckets don't change."""
        self.kz_partitioner.acquired = True
        self.kz_partitioner.__iter__.return_value = [2, 3]
        self.partitioner.startService()
        self.clock.advance(10)
        self.clock.advance(10)
        self.log.msg.assert_called_once_with(
            'Got buckets {buckets}',
            buckets=[2, 3], old_buckets=[], path=self.path,
            otter_msg_type='partition-acquired')

    def test_log_on_difference(self):
        """Bucket changes are logged when the buckets change."""
        self.kz_partitioner.acquired = True
        self.kz_partitioner.__iter__.return_value = [2, 3]
        self.partitioner.startService()
        self.log.msg.assert_called_once_with(
            'Got buckets {buckets}',
            buckets=[2, 3], old_buckets=[], path=self.path,
            otter_msg_type='partition-acquired')
        self.kz_partitioner.__iter__.return_value = [3, 4]
        self.clock.advance(10)
        self.log.msg.assert_called_with(
            'Got buckets {buckets}',
            buckets=[3, 4], old_buckets=[2, 3], path=self.path,
            otter_msg_type='partition-acquired')

    def test_stop_service_not_acquired(self):
        """
        stopService() does not stop the allocation (i.e. call finish) if
        it is not acquired.
        """
        self.kz_partitioner.allocating = True
        self.partitioner.startService()
        d = self.partitioner.stopService()
        self.assertFalse(self.kz_partitioner.finish.called)
        self.successResultOf(d)

    def test_stop_service_acquired(self):
        """
        stopService() calls ``finish`` on the partitioner if it is acquired.
        """
        self.kz_partitioner.acquired = True
        self.partitioner.startService()
        d = self.partitioner.stopService()
        self.assertIs(self.successResultOf(d),
                      self.kz_partitioner.finish.return_value)

    def test_stop_service_stops_polling(self):
        """
        stopService causes the service to stop checking the partitioner every
        interval.
        """
        self.kz_partitioner.allocating = True
        self.partitioner.startService()
        self.kz_partitioner.acquired = True
        self.kz_partitioner.allocating = False
        self.kz_partitioner.__iter__.return_value = iter([2, 3])
        self.partitioner.stopService()
        self.assertEqual(self.partitioner.running, False)
        self.clock.advance(10)
        self.assertEqual(self.buckets_received, [])

    def test_reset_path(self):
        """``reset_path`` creates a new partitioner at the given path."""
        self.partitioner.reset_path('/new_path')
        self.assertEqual(self.partitioner.partitioner_path, '/new_path')
        self.kz_client.SetPartitioner.assert_called_once_with(
            '/new_path',
            set=self.buckets,
            time_boundary=self.time_boundary)
        self.assertEqual(self.partitioner.partitioner,
                         self.kz_client.SetPartitioner.return_value)

    def test_health_check_not_running(self):
        """When the service isn't running, the service is unhealthy."""
        self.assertEqual(
            self.successResultOf(self.partitioner.health_check()),
            (False, {'reason': 'Not running'}))

    def test_health_check_not_acquired(self):
        """When the buckets aren't acquired, the service is unhealthy."""
        self.kz_partitioner.allocating = True
        self.partitioner.startService()
        self.assertEqual(
            self.successResultOf(self.partitioner.health_check()),
            (False, {'reason': 'Not acquired'}))

    def test_health_check_acquired(self):
        """When the buckets are acquired, they're included in the info."""
        self.kz_partitioner.acquired = True
        self.partitioner.startService()
        self.kz_partitioner.__iter__.return_value = iter([2, 3])
        self.assertEqual(
            self.successResultOf(self.partitioner.health_check()),
            (True, {'buckets': [2, 3]}))

    def test_get_current_buckets(self):
        """The current buckets can be retrieved."""
        self.kz_partitioner.acquired = True
        self.partitioner.startService()
        self.kz_partitioner.__iter__.return_value = iter([2, 3])
        self.assertEqual(self.partitioner.get_current_buckets(), [2, 3])

    def test_get_current_state(self):
        """The current state can be retrieved."""
        self.kz_partitioner.state = PartitionState.ACQUIRED
        self.partitioner.startService()
        self.assertEqual(self.partitioner.get_current_state(),
                         PartitionState.ACQUIRED)
