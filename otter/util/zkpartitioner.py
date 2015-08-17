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
    and ``buckets``, and each server will get a disjoint subset of ``buckets``
    allocated to them.

    In order to be notified of which buckets are allocated to the current node,
    a ``got_buckets`` function must be passed in which will be called when the
    local buckets have been determined.
    """
    def __init__(self, kz_client, interval, partitioner_path, buckets,
                 time_boundary, log, got_buckets,
                 clock=None):
        """
        :param log: a bound log
        :param kz_client: txKazoo client
        :param partitioner_path: ZooKeeper path, used for partitioning
        :param buckets: iterable of buckets to distribute between
            nodes. Ideally there should be at least as many elements as nodes
            taking part in this partitioner. This should be a sequence of str.
        :param time_boundary: time to wait for partitioning to stabilize.
        :param got_buckets: Callable which will be called with a list of
            buckets when buckets have been allocated to this node.
        :param clock: clock to use for checking the buckets on an interval.
        """
        MultiService.__init__(self)
        self.kz_client = kz_client
        self.partitioner_path = partitioner_path
        self.buckets = buckets
        self.log = log
        self.got_buckets = got_buckets
        self.time_boundary = time_boundary
        ts = TimerService(interval, self.check_partition)
        ts.setServiceParent(self)
        ts.clock = clock
        self._old_buckets = []

    def get_current_state(self):
        """Return the current partitioner state."""
        return self.partitioner.state

    def _new_partitioner(self):
        return self.kz_client.SetPartitioner(
            self.partitioner_path,
            set=self.buckets,
            time_boundary=self.time_boundary)

    def startService(self):
        """Start partitioning."""
        # Create the partitioner *before* up-calling, because otherwise the
        # TimerService may call `check_partition` before self.partitioner is
        # created.
        self.partitioner = self._new_partitioner()
        super(Partitioner, self).startService()

    def stopService(self):
        """Release the buckets."""
        d = super(Partitioner, self).stopService()
        if self.partitioner.acquired:
            d.addCallback(lambda _: self.partitioner.finish())
        return d

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
                    self.get_current_state()),
                otter_msg_type='partition-invalid-state')
            self.partitioner.finish()
            self.partitioner = self._new_partitioner()
            return

        buckets = self.get_current_buckets()
        if buckets != self._old_buckets:
            self.log.msg('Got buckets {buckets}', buckets=buckets,
                         path=self.partitioner_path,
                         old_buckets=self._old_buckets,
                         otter_msg_type='partition-acquired')
            self._old_buckets = buckets
        return self.got_buckets(buckets)

    def health_check(self):
        """
        Do a health check on the partitioner service.

        :return: a Deferred that fires with (Bool, `dict` of extra info).
        """
        if not self.running:
            return succeed((False, {'reason': 'Not running'}))

        if not self.partitioner.acquired:
            # TODO: Until there is check added for not being allocated for too
            # long, it is fine to indicate the service is not healthy when it
            # is allocating, since allocating should happen only on start-up or
            # during network issues.
            return succeed((False, {'reason': 'Not acquired'}))

        return succeed((True, {'buckets': self.get_current_buckets()}))

    def get_current_buckets(self):
        """
        Retrieve the current buckets as a list.

        This should only be relied on when the current partitioner state is
        ``ACQUIRED``.
        """
        return list(self.partitioner)
