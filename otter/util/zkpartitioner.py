"""
ZooKeeper set-partitioning stuff.
"""

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import succeed


class Partitioner(MultiService, object):
    """
    A Twisted service which uses a Kazoo :obj:`SetPartitioner` to allocate
    logical ``buckets`` between nodes.

    Multiple servers can instantiate these with the same ``partitioner_path``
    and ``num_buckets``, and each server will get a disjoint subset of
    ``range(buckets)`` allocated to them.

    In order to be notified of which buckets are allocated to the current node,
    a ``got_buckets`` function must be passed in which will be called when the
    local buckets have been determined.
    """
    def __init__(self, log, kz_client,
                 interval,
                 partitioner_path, num_buckets, time_boundary,
                 got_buckets):
        """
        :param log: a bound log
        :param kz_client: txKazoo client
        :param partitioner_path: ZooKeeper path, used for partitioning
        :param int num_buckets: number of logical buckets to distribute between
            nodes. This should be at least the number of nodes taking part in
            this partitioner.
        :param time_boundary: time to wait for partitioning to stabilize.
        :param got_buckets: Callable which will be called with a list of
            buckets when buckets have been allocated to this node.
        """
        self.kz_client = kz_client
        self.partitioner_path = partitioner_path
        self.num_buckets = num_buckets
        self.log = log
        self.got_buckets = got_buckets
        ts = TimerService(interval, self.check_partition)
        ts.setServiceParent(self)

    def _new_partitioner(self):
        return self.kz_client.SetPartitioner(
            self.partitioner_path,
            set=set(map(str, range(self.num_buckets))),
            time_boundary=self.time_boundary)

    def startService(self):
        """Start partitioning."""
        super(Partitioner, self).startService()
        self.partitioner = self._new_partitioner()

    def stopService(self):
        """Release the buckets."""
        if self.partitioner.acquired:
            return self.partitioner.finish()

    def reset_path(self, path):
        """Re-initialize the partitioner to use a new path."""
        if self.partitioner_path != path:
            self.partitioner_path = path
            self.partitioner = self._new_partitioner()
        else:
            raise ValueError('same path')

    def check_partition(self):
        """
        Step through the SetPartitioner state machine, and once everything is
        sorted out, call the ``got_buckets`` function with the buckets that
        have been allocated to this node.
        """
        if self.partitioner.allocating:
            self.log.msg('Partition allocating',
                         otter_msg_type='partition-allocating')
            return
        if self.partitioner.release:
            self.log.msg('Partition changed. Repartitioning',
                         otter_msg_type='partition-released')
            return self.partitioner.release_set()
        if self.partitioner.failed:
            self.log.msg('Partition failed. Starting new',
                         otter_msg_type='partition-failed')
            self.partitioner = self._new_partitioner()
            return
        if not self.partitioner.acquired:
            self.log.err(
                'Unknown state {}. This cannot happen. Starting new'.format(
                    self.partitioner.state),
                otter_msg_type='partition-invalid-state')
            self.partitioner.finish()
            self.partitioner = self._new_partitioner()
            return

        buckets = self.get_current_buckets()
        # TODO: This log might feel like spam since it'll occur on every
        # tick. But it'll be useful to debug partitioning problems (at least in
        # initial deployment)
        self.log.msg('Got buckets {buckets}', buckets=buckets,
                     path=self.partitioner_path)
        self.got_buckets(buckets)

    def health_check(self):
        """
        Do a health check on the partitioner service.

        :return: a Deferred that fires with (Bool, `dict` of extra debug info).
        """
        if not self.running:
            return succeed((False, {'reason': 'Not running'}))

        if not self.partitioner.acquired:
            # TODO: Until there is check added for not being allocated for long
            # time it is fine to assume service is not healthy when it is
            # allocating since allocating should happen only on deploy or
            # network issues
            return succeed((False, {'reason': 'Not acquired'}))

        return succeed((True, {}))

    def get_current_buckets(self):
        """Retrieve the current buckets as a list."""
        return list(self.partitioner)

# def test_check_events_allocating(self):
#     """
#     `check_events` logs message and does not check events in buckets
#     when buckets are still allocating.
#     """
#     self.kz_partition.allocating = True
#     self._start_service()
#     self.scheduler_service.check_events(100)
#     self.log.msg.assert_called_with('Partition allocating')

#     # Ensure others are not called
#     self.assertFalse(self.kz_partition.__iter__.called)
#     self.assertFalse(self.check_events_in_bucket.called)

# def test_check_events_release(self):
#     """
#     `check_events` logs message and does not check events in buckets
#     when partitioning has changed. It calls release_set() to
#     re-partition.
#     """
#     self.kz_partition.release = True
#     self._start_service()
#     self.scheduler_service.check_events(100)
#     self.log.msg.assert_called_with('Partition changed. Repartitioning')
#     self.kz_partition.release_set.assert_called_once_with()

#     # Ensure others are not called
#     self.assertFalse(self.kz_partition.__iter__.called)
#     self.assertFalse(self.check_events_in_bucket.called)

# def test_check_events_failed(self):
#     """
#     `check_events` logs message and does not check events in buckets
#     when partitioning has failed. It creates a new partition.
#     """
#     self.kz_partition.failed = True
#     self._start_service()

#     # after starting change SetPartitioner return value to check if
#     # new value is set in self.scheduler_service.kz_partition
#     new_kz_partition = mock.MagicMock()
#     self.kz_client.SetPartitioner.return_value = new_kz_partition

#     self.scheduler_service.check_events(100)
#     self.log.msg.assert_called_with('Partition failed. Starting new')

#     # Called once when starting and now again when partition failed
#     self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
#                      [mock.call(self.zk_partition_path,
#                                 set=set(range(self.num_buckets)),
#                                 time_boundary=self.time_boundary)] * 2)
#     self.assertEqual(self.scheduler_service.kz_partition, new_kz_partition)

#     # Ensure others are not called
#     self.assertFalse(self.kz_partition.__iter__.called)
#     self.assertFalse(new_kz_partition.__iter__.called)
#     self.assertFalse(self.check_events_in_bucket.called)

# def test_check_events_bad_state(self):
#     """`self.kz_partition.state` is none of the exepected values.

#     `check_events` logs it as err and starts a new partition

#     """
#     self.kz_partition.state = 'bad'
#     self._start_service()

#     # after starting change SetPartitioner return value to check if
#     # new value is set in self.scheduler_service.kz_partition
#     new_kz_partition = mock.MagicMock()
#     self.kz_client.SetPartitioner.return_value = new_kz_partition

#     self.scheduler_service.check_events(100)

#     self.log.err.assert_called_with(
#         'Unknown state bad. This cannot happen. Starting new')
#     self.kz_partition.finish.assert_called_once_with()

#     # Called once when starting and now again when got bad state
#     self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
#                      [mock.call(self.zk_partition_path,
#                                 set=set(range(self.buckets)),
#                                 time_boundary=self.time_boundary)] * 2)
#     self.assertEqual(self.scheduler_service.kz_partition, new_kz_partition)

#     # Ensure others are not called
#     self.assertFalse(self.kz_partition.__iter__.called)
#     self.assertFalse(new_kz_partition.__iter__.called)
#     self.assertFalse(self.check_events_in_bucket.called)

# def test_get_buckets(self):
#     log.msg.assert_called_once_with('Got buckets {buckets}',
#                                     buckets=[2, 3], path='/part_path')

# def test_stop_service_allocating(self):
#     """
#     stopService() does not stop the allocation (i.e. call finish) if
#     it is not acquired.
#     """
#     self._start_service()
#     d = self.scheduler_service.stopService()
#     self.assertFalse(self.kz_partition.finish.called)
#     self.assertIsNone(d)

# def test_reset_path(self):
#     self.assertEqual(self.scheduler_service.zk_partition_path, '/new_path')
#     self.kz_client.SetPartitioner.assert_called_once_with(
#         '/new_path',
#         set=set(range(self.num_buckets)),
#         time_boundary=self.time_boundary)
#     self.assertEqual(self.scheduler_service.kz_partition,
#                      self.kz_client.SetPartitioner.return_value)
