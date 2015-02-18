"""
ZooKeeper set-partitioning stuff.
"""

from twisted.application.internet import TimerService
from twisted.application.service import MultiService, Service


class Partitioner(Service, object):
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

    def _new_partitioner(self):
        return self.kz_client.SetPartitioner(
            self.partitioner_path,
            set=set(map(str, range(self.num_buckets))),
            time_boundary=self.time_boundary)

    def startService(self):
        """Start partitioning."""
        self.partitioner = self._new_partitioner()
        super(Partitioner, self).startService()

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

        buckets = list(self.partitioner)
        self.got_buckets(buckets)


def make_partitioner_service(interval,
                             log, kz_client, path, num_buckets, time_boundary,
                             got_buckets):
    """Return a service which encapsulates a partitioner."""
    ms = MultiService()
    ps = Partitioner(log, kz_client, path, num_buckets, time_boundary,
                     got_buckets)
    ts = TimerService(interval)
    ps.setServiceParent(ms)
    ts.setServiceParent(ms)
    return ms
