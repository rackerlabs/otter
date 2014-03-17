
    def test_check_events_allocating(self):
        """
        `check_events` logs message and does not check events in buckets when
        buckets are still allocating
        """
        self.kz_partition.allocating = True
        self.sservice.startService()
        self.sservice.check_events(100)
        self.log.msg.assert_called_with('Partition allocating')

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_release(self):
        """
        `check_events` logs message and does not check events in buckets when
        partitioning has changed. It calls release_set() to re-partition
        """
        self.kz_partition.release = True
        self.sservice.startService()
        self.sservice.check_events(100)
        self.log.msg.assert_called_with('Partition changed. Repartitioning')
        self.kz_partition.release_set.assert_called_once_with()

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_failed(self):
        """
        `check_events` logs message and does not check events in buckets when
        partitioning has failed. It creates a new partition
        """
        self.kz_partition.failed = True
        self.sservice.startService()

        # after starting change SetPartitioner return value to check if
        # new value is set in self.sservice.kz_partition
        new_kz_partition = mock.MagicMock()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.sservice.check_events(100)
        self.log.msg.assert_called_with('Partition failed. Starting new')

        # Called once when starting and now again when partition failed
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.zk_partition_path, set=set(self.buckets),
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.sservice.kz_partition, new_kz_partition)

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(new_kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_bad_state(self):
        """
        `self.kz_partition.state` is none of the exepected values. `check_events`
        logs it as err and starts a new partition
        """
        self.kz_partition.state = 'bad'
        self.sservice.startService()

        # after starting change SetPartitioner return value to check if
        # new value is set in self.sservice.kz_partition
        new_kz_partition = mock.MagicMock()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.sservice.check_events(100)

        self.log.err.assert_called_with('Unknown state bad. This cannot happen. Starting new')
        self.kz_partition.finish.assert_called_once_with()

        # Called once when starting and now again when got bad state
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.zk_partition_path, set=set(self.buckets),
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.sservice.kz_partition, new_kz_partition)

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(new_kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    @mock.patch('otter.scheduler.datetime')
    def test_check_events_acquired(self, mock_datetime):
        """
        `check_events` checks events in each bucket when they are partitoned.
        """
        self.kz_partition.acquired = True
        self.sservice.startService()
        self.kz_partition.__iter__.return_value = [2, 3]
        self.sservice.log = mock.Mock()
        mock_datetime.utcnow.return_value = 'utcnow'

        responses = [4, 5]
        self.check_events_in_bucket.side_effect = lambda *_: defer.succeed(responses.pop(0))

        d = self.sservice.check_events(100)

        self.assertEqual(self.successResultOf(d), [4, 5])
        self.assertEqual(self.kz_partition.__iter__.call_count, 1)
        self.sservice.log.bind.assert_called_once_with(
            scheduler_run_id='transaction-id', utcnow='utcnow')
        log = self.sservice.log.bind.return_value
        log.msg.assert_called_once_with('Got buckets {buckets}', buckets=[2, 3])
        self.assertEqual(self.check_events_in_bucket.mock_calls,
                         [mock.call(log, self.mock_store, 2, 'utcnow', 100),
                          mock.call(log, self.mock_store, 3, 'utcnow', 100)])

