"""
Tests for otter/partition.py
"""

import mock
from StringIO import StringIO

from twisted.trial.unittest import TestCase

from kazoo.recipe.partitioner import SetPartitioner

from otter.test.utils import patch

from otter.partition import partition, process_partitioner, main


class ProcessPartitionerTests(TestCase):
    """
    Tests for `process_partitioner`
    """

    def setUp(self):
        """
        Sample SetPartitioner
        """
        self.part = mock.MagicMock(
            spec=SetPartitioner, allocating=False, release=False, failed=False,
            acquired=False)
        self.new_part = mock.Mock()
        sys = patch(self, 'otter.partition.sys', spec=['stdout'])
        self.strio = StringIO()
        self.stdout = sys.stdout = mock.Mock(wraps=self.strio)

    def test_allocating(self):
        """
        Waits to acquire when allocating and does nothing else
        """
        self.part.allocating = True
        p = process_partitioner(self.part, self.new_part)
        self.assertEqual(p, self.part)
        self.part.wait_for_acquire.assert_called_once_with()
        self.assertFalse(self.new_part.called)
        self.assertFalse(self.part.release_set.called)
        self.assertFalse(self.part.__iter__.called)
        self.assertEqual(self.strio.getvalue(), '')

    def test_release(self):
        """
        calls release_set() when in release state and does nothing else
        """
        self.part.release = True
        p = process_partitioner(self.part, self.new_part)
        self.assertEqual(p, self.part)
        self.part.release_set.assert_called_once_with()
        self.assertFalse(self.new_part.called)
        self.assertFalse(self.part.wait_for_acquire.called)
        self.assertFalse(self.part.__iter__.called)
        self.assertEqual(self.strio.getvalue(), '')

    def test_failed(self):
        """
        creates new partitioner when failed and does nothing else
        """
        self.part.failed = True
        p = process_partitioner(self.part, self.new_part)
        self.assertNotEqual(p, self.part)
        self.assertEqual(p, self.new_part.return_value)
        self.new_part.assert_called_once_with()
        self.assertFalse(self.part.release_set.called)
        self.assertFalse(self.part.wait_for_acquire.called)
        self.assertFalse(self.part.__iter__.called)
        self.assertEqual(self.strio.getvalue(), '')

    def test_acquired(self):
        """
        writes buckets json to stdout when acquired and does nothing else
        """
        self.part.acquired = True
        self.part.__iter__.return_value = [1, 2]
        p = process_partitioner(self.part, self.new_part)
        self.assertEqual(self.strio.getvalue(), '{"buckets": [1, 2]}\n')
        self.stdout.flush.assert_called_once_with()
        self.assertEqual(p, self.part)
        self.assertFalse(self.new_part.called)
        self.assertFalse(self.part.release_set.called)
        self.assertFalse(self.part.wait_for_acquire.called)


class PartitionTests(TestCase):
    """
    Tests for `partition()`
    """

    def setUp(self):
        """
        Sample client
        """
        self.client = mock.Mock(spec=['SetPartitioner'])
        self.part = mock.MagicMock(
            spec=SetPartitioner, allocating=False, release=False, failed=False,
            acquired=False)
        self.client.SetPartitioner.return_value = self.part

        self.running = [True, False]
        self.running_func = lambda: self.running.pop(0)

        time = patch(self, 'otter.partition.time', spec=['sleep'])
        self.sleep = time.sleep

        self.proc_part = patch(self, 'otter.partition.process_partitioner',
                               return_value=self.part)

    def test_sleep_on_acquired(self):
        """
        Sleeps when acquired
        """
        self.part.acquired = True
        partition(self.client, '/path', [1, 2], 10, 1, running=self.running_func)
        self.client.SetPartitioner.assert_called_once_with('/path', [1, 2], time_boundary=10)
        self.proc_part.assert_called_once_with(self.part, mock.ANY)
        # second argument is function that creates new SetPartitioner
        p = self.proc_part.call_args[0][1]()
        self.assertEqual(p, self.part)
        # Sleeps since acquired
        self.sleep.assert_called_once_with(1)

    def test_not_sleep_on_non_acquired(self):
        """
        Does not sleep when not acquired
        """
        partition(self.client, '/path', [1, 2], 10, 1, running=self.running_func)
        self.client.SetPartitioner.assert_called_once_with('/path', [1, 2], time_boundary=10)
        self.proc_part.assert_called_once_with(self.part, mock.ANY)
        # second argument is function that creates new SetPartitioner
        p = self.proc_part.call_args[0][1]()
        self.assertEqual(p, self.part)
        # Does not sleep
        self.assertFalse(self.sleep.called)

    def test_loop_continues(self):
        """
        Loop continues to run
        """
        self.running = [True, True, False]
        partition(self.client, '/path', [1, 2], 10, 1, running=self.running_func)
        self.client.SetPartitioner.assert_called_once_with('/path', [1, 2], time_boundary=10)
        self.assertEqual(self.proc_part.call_count, 2)
        self.assertFalse(self.sleep.called)


class MainTests(TestCase):
    """
    Tests for `main()`
    """

    def setUp(self):
        """
        Mock KazooClient and partition
        """
        self.client = patch(self, 'otter.partition.KazooClient')
        self.shandler = patch(self, 'otter.partition.SequentialThreadingHandler')
        self.ghandler = patch(self, 'otter.partition.SequentialGeventHandler')
        self.part = patch(self, 'otter.partition.partition')
        self.args = ['kz_hosts', '/path', '1,2,3', '2.3', '3.4']

    def _test_client(self, handler):
        """
        Check KazooClient is created and partition is called correctly
        """
        handler.assert_called_once_with()
        self.client.assert_called_once_with(hosts='kz_hosts', handler=handler.return_value)
        self.client.return_value.start.assert_called_once_with()
        self.part.assert_called_once_with(self.client.return_value,
                                          '/path', set(['1', '2', '3']), 2.3, 3.4)

    def test_thread_handler(self):
        """
        SequentialThreadingHandler is used when first arg is 'thread'
        """
        main(['thread'] + self.args)
        self._test_client(self.shandler)

    def test_gevent_handler(self):
        """
        SequentialGeventHandler is used when first arg is 'gevent'
        """
        main(['gevent'] + self.args)
        self._test_client(self.ghandler)
