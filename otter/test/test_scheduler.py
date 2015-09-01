"""
Tests for :mod:`otter.scheduler`
"""
from datetime import datetime, timedelta

import mock

from twisted.internet import defer
from twisted.trial.unittest import SynchronousTestCase

from otter.controller import CannotExecutePolicyError
from otter.models.interface import (
    IScalingGroup,
    IScalingGroupCollection,
    IScalingScheduleCollection,
    NoSuchPolicyError,
    NoSuchScalingGroupError
)
from otter.scheduler import (
    SchedulerService,
    add_cron_events,
    check_events_in_bucket,
    execute_event,
    process_events
)
from otter.test.utils import (
    CheckFailure,
    DeferredFunctionMixin,
    FakePartitioner,
    IsBoundWith,
    iMock,
    matches,
    mock_log,
    patch
)


class SchedulerTests(SynchronousTestCase):
    """
    Tests for `scheduler.py`.
    """

    def setUp(self):
        """
        Mock common dependencies of methods in scheduler.py.
        """
        self.mock_store = iMock(
            IScalingGroupCollection, IScalingScheduleCollection)
        self.mock_generate_transaction_id = patch(
            self, 'otter.scheduler.generate_transaction_id',
            return_value='transaction-id')


class SchedulerServiceTests(SchedulerTests, DeferredFunctionMixin):
    """
    Tests for `SchedulerService`.
    """

    def setUp(self):
        """
        Mock all the dependencies of SchedulingService.

        This includes logging, store's fetch_and_delete, TxKazooClient stuff,
        check_events_in_bucket.
        """
        super(SchedulerServiceTests, self).setUp()

        otter_log = patch(self, 'otter.scheduler.otter_log')
        self.log = mock_log()
        otter_log.bind.return_value = self.log

        def pfactory(log, callable):
            self.fake_partitioner = FakePartitioner(log, callable)
            return self.fake_partitioner

        self.scheduler_service = SchedulerService(
            "disp", 100, self.mock_store, pfactory, threshold=600)
        otter_log.bind.assert_called_once_with(system='otter.scheduler')
        self.scheduler_service.running = True
        self.assertIdentical(self.fake_partitioner,
                             self.scheduler_service.partitioner)

        self.check_events_in_bucket = patch(
            self, 'otter.scheduler.check_events_in_bucket')

        self.returns = []
        self.setup_func(self.mock_store.get_oldest_event)

    def test_partitioner_child(self):
        """
        The Partitioner service is registered as a child of the
        SchedulerService.
        """
        self.assertEqual(self.scheduler_service.services,
                         [self.fake_partitioner])

    def test_health_check_after_threshold(self):
        """
        `service.health_check` returns False when trigger time is above
        threshold.
        """
        self.fake_partitioner.health = (True, {'buckets': [2, 3]})
        now = datetime.utcnow()
        returns = [{'trigger': now - timedelta(hours=1), 'version': 'v1'},
                   {'trigger': now - timedelta(seconds=2), 'version': 'v1'}]
        self.returns = returns[:]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d),
                         (False, {'old_events': [returns[0]],
                                  'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls(
            [mock.call(2), mock.call(3)])

    def test_health_check_before_threshold(self):
        """
        `service.health_check` returns True when trigger time is below
        threshold.
        """
        self.fake_partitioner.health = (True, {'buckets': [2, 3]})
        now = datetime.utcnow()
        self.returns = [{'trigger': now + timedelta(hours=1),
                         'version': 'v1'},
                        {'trigger': now + timedelta(seconds=2),
                         'version': 'v1'}]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d), (True, {'old_events': [],
                                                          'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls(
            [mock.call(2), mock.call(3)])

    def test_health_check_None(self):
        """
        `service.health_check` returns True when there are no triggers.
        """
        self.fake_partitioner.health = (True, {'buckets': [2, 3]})
        self.returns = [None, None]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d),
                         (True, {'old_events': [], 'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls(
            [mock.call(2), mock.call(3)])

    def test_health_check_unhealthy_partitioner(self):
        """
        When the partitioner service is unhealthy, the scheduler service passes
        its health message through.
        """
        self.fake_partitioner.health = (False, {'foo': 'bar'})
        d = self.scheduler_service.health_check()
        self.assertEqual(self.successResultOf(d),
                         (False, {'foo': 'bar'}))

    def test_health_check_not_running(self):
        """
        `service.health_check` returns False when scheduler is stopped.
        """
        self.scheduler_service.running = False
        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d),
                         (False, {'reason': 'Not running'}))
        self.assertFalse(self.mock_store.get_oldest_event.called)

    def test_reset(self):
        """
        reset() starts new partition based on new path.
        """
        self.assertEqual(
            self.scheduler_service.reset('/new_path'),
            'partitioner reset to /new_path')

    @mock.patch('otter.scheduler.datetime')
    def test_check_events_acquired(self, mock_datetime):
        """
        the got_buckets callback checks events in each bucket when they are
        partitoned.
        """
        self.scheduler_service.log = mock.Mock()
        mock_datetime.utcnow.return_value = 'utcnow'

        responses = [4, 5]
        self.check_events_in_bucket.side_effect = \
            lambda *_: defer.succeed(responses.pop(0))

        d = self.fake_partitioner.got_buckets([2, 3])

        self.assertEqual(self.successResultOf(d), [4, 5])
        self.scheduler_service.log.bind.assert_called_once_with(
            scheduler_run_id='transaction-id', utcnow='utcnow')
        log = self.scheduler_service.log.bind.return_value
        self.assertEqual(self.check_events_in_bucket.mock_calls,
                         [mock.call(log, "disp", self.mock_store, 2,
                                    'utcnow', 100),
                          mock.call(log, "disp", self.mock_store, 3,
                                    'utcnow', 100)])


class CheckEventsInBucketTests(SchedulerTests):
    """
    Tests for `check_events_in_bucket`
    """

    def setUp(self):
        """
        Mock store.fetch_and_delete and `process_events`
        """
        super(CheckEventsInBucketTests, self).setUp()

        self.returns = [[]]

        def _responses(*args):
            result = self.returns.pop(0)
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.mock_store.fetch_and_delete.side_effect = _responses
        self.process_events = patch(
            self, 'otter.scheduler.process_events',
            side_effect=lambda e, d, s, l: defer.succeed(len(e)))
        self.log = mock.Mock()

    def test_fetch_called(self):
        """
        `fetch_and_delete` called correctly
        """
        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'utcnow', 100)
        self.successResultOf(d)
        self.mock_store.fetch_and_delete.assert_called_once_with(
            1, 'utcnow', 100)
        self.log.bind.assert_called_once_with(bucket=1)

    def test_no_events(self):
        """When no events are fetched, they are not processed."""
        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'utcnow', 100)
        self.successResultOf(d)
        self.process_events.assert_called_once_with(
            [], "disp", self.mock_store, self.log.bind())

    def test_events_in_limit(self):
        """
        When events fetched < 100, they are processed
        """
        events = [{'tenantId': '1234',
                   'groupId': 'scal44',
                   'policyId': 'pol4{}'.format(i),
                   'trigger': 'now',
                   'cron': None,
                   'bucket': 1}
                  for i in range(10)]
        self.returns = [events]

        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'utcnow', 100)

        self.successResultOf(d)
        # Ensure fetch_and_delete and process_events is called only once
        self.mock_store.fetch_and_delete.assert_called_once_with(
            1, 'utcnow', 100)
        self.process_events.assert_called_once_with(
            events, "disp", self.mock_store, self.log.bind())

    def test_events_process_error(self):
        """
        Error is logged if `process_events` returns error.
        """
        self.returns = [ValueError('e')]

        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'utcnow', 100)

        self.successResultOf(d)
        self.log.bind.return_value.err.assert_called_once_with(
            CheckFailure(ValueError))
        self.assertFalse(self.process_events.called)

    def test_events_more_limit(self):
        """When events fetched > 100, they are processed in 2 batches."""
        events1 = [{'tenantId': '1234',
                    'groupId': 'scal44',
                    'policyId': 'pol4{}'.format(i),
                    'trigger': 'now',
                    'cron': None,
                    'bucket': 1}
                   for i in range(100)]
        events2 = [{'tenantId': '1235',
                    'groupId': 'scal54',
                    'policyId': 'pol4{}'.format(i),
                    'trigger': 'now',
                    'cron': None,
                    'bucket': 1}
                   for i in range(10)]
        self.returns = [events1, events2]

        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'now', 100)

        self.successResultOf(d)
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 2)
        self.assertEqual(self.process_events.mock_calls,
                         [mock.call(events1,
                                    "disp",
                                    self.mock_store,
                                    self.log.bind()),
                          mock.call(events2,
                                    "disp",
                                    self.mock_store,
                                    self.log.bind())])

    def test_events_batch_error(self):
        """
        When error occurs after first batch of events are processed, then it
        logs errors and does not try to fetch again.
        """
        events = [{'tenantId': '1234',
                   'groupId': 'scal44',
                   'policyId': 'pol4{}'.format(i),
                   'trigger': 'now',
                   'cron': None,
                   'bucket': 1}
                  for i in range(100)]
        self.returns = [events, ValueError('some')]

        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'now', 100)

        self.successResultOf(d)
        self.log.bind.return_value.err.assert_called_once_with(
            CheckFailure(ValueError))
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 2)
        self.process_events.assert_called_once_with(events, "disp",
                                                    self.mock_store,
                                                    self.log.bind())

    def test_events_batch_process(self):
        """
        When events fetched > 100, they are processed in batches until all
        events are processed
        """
        events1 = [{'tenantId': '1234',
                    'groupId': 'scal44',
                    'policyId': 'pol4{}'.format(i),
                    'trigger': 'now',
                    'cron': None,
                    'bucket': 1} for i in range(100)]
        events2 = [{'tenantId': '1235',
                    'groupId': 'scal54',
                    'policyId': 'pol4{}'.format(i),
                    'trigger': 'now',
                    'cron': None,
                    'bucket': 1} for i in range(100)]
        events3 = [{'tenantId': '1236',
                    'groupId': 'scal64',
                    'policyId': 'pol4{}'.format(i),
                    'trigger': 'now',
                    'cron': None,
                    'bucket': 1} for i in range(10)]
        self.returns = [events1, events2, events3]

        d = check_events_in_bucket(self.log, "disp", self.mock_store, 1,
                                   'now', 100)

        self.successResultOf(d)
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 3)
        self.assertEqual(self.process_events.mock_calls,
                         [mock.call(events, "disp", self.mock_store,
                                    self.log.bind())
                          for events in [events1, events2, events3]])


class ProcessEventsTests(SchedulerTests):
    """
    Tests for `process_events`.
    """

    def setUp(self):
        """
        Mock `execute_event` and `add_cron_events`.
        """
        super(ProcessEventsTests, self).setUp()
        self.execute_event = patch(self, 'otter.scheduler.execute_event',
                                   return_value=defer.succeed(None))

        def fake_add_cron_events(store, log, events, deleted_policy_ids):
            return defer.succeed(events)

        self.add_cron_events = patch(
            self, 'otter.scheduler.add_cron_events',
            side_effect=fake_add_cron_events)
        self.log = mock_log()

    def test_no_events(self):
        """
        Does nothing on no events.
        """
        r = process_events([], "disp", self.mock_store, self.log)
        self.assertEqual(r, 0)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.execute_event.called)
        self.assertFalse(self.add_cron_events.called)

    def test_success(self):
        """
        Test success path: Logs number of events, calls `execute_event` on
        each event and calls `add_cron_events.`
        """
        events = range(10)
        d = process_events(events, "disp", self.mock_store, self.log)
        self.assertEqual(self.successResultOf(d), 10)
        self.log.msg.assert_called_once_with(
            'Processing {num_events} events', num_events=10)
        self.assertEqual(
            self.execute_event.mock_calls,
            [mock.call("disp", self.mock_store, self.log, event, set())
             for event in events])
        self.add_cron_events.assert_called_once_with(
            self.mock_store, self.log, events, set())


class AddCronEventsTests(SchedulerTests):
    """
    Tests for `add_cron_events`.
    """

    def setUp(self):
        """
        Mock store.add_cron_events and next_cron_occurrence.
        """
        super(AddCronEventsTests, self).setUp()
        self.mock_store.add_cron_events.return_value = defer.succeed(None)
        self.next_cron_occurrence = patch(
            self, 'otter.scheduler.next_cron_occurrence',
            return_value='next')
        self.log = mock_log()

    def test_no_events(self):
        """
        Does nothing on no events.
        """
        d = add_cron_events(self.mock_store, self.log, [], set())
        self.assertIsNone(d)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.next_cron_occurrence.called)
        self.assertFalse(self.mock_store.add_cron_events.called)

    def test_no_events_to_add(self):
        """
        When all events passed are to be deleted, then does nothing
        """
        events = [{'tenantId': '1234',
                   'groupId': 'scal44',
                   'policyId': 'pol4{}'.format(i),
                   'trigger': 'now',
                   'cron': '*',
                   'bucket': 1}
                  for i in range(3)]
        d = add_cron_events(self.mock_store, self.log, events,
                            set(['pol4{}'.format(i) for i in range(3)]))
        self.assertIsNone(d)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.next_cron_occurrence.called)
        self.assertFalse(self.mock_store.add_cron_events.called)

    def test_store_add_cron_called(self):
        """
        Updates cron events for non-deleted policies by calling
        store.add_cron_events.
        """
        events = [{'tenantId': '1234',
                   'groupId': 'scal44',
                   'policyId': 'pol4{}'.format(i),
                   'trigger': 'now',
                   'cron': '*',
                   'bucket': 1}
                  for i in range(10)]
        deleted_policy_ids = set(['pol41', 'pol45'])
        new_events = events[:]
        new_events.pop(1)
        new_events.pop(4)
        [event.update({'trigger': 'next'}) for event in new_events]

        d = add_cron_events(
            self.mock_store, self.log, events, deleted_policy_ids)

        self.assertIsNone(self.successResultOf(d), None)
        self.assertEqual(self.next_cron_occurrence.call_count, 8)
        self.mock_store.add_cron_events.assert_called_once_with(new_events)


class ExecuteEventTests(SchedulerTests):
    """
    Tests for `execute_event`.
    """

    def setUp(self):
        """
        Mock execution of scaling policy.
        """
        super(ExecuteEventTests, self).setUp()
        self.mock_group = iMock(IScalingGroup)
        self.mock_store.get_scaling_group.return_value = self.mock_group

        # mock out modify_and_trigger
        self.mock_mt = patch(self, "otter.scheduler.modify_and_trigger")
        self.new_state = None

        def _set_new_state(new_state):
            self.new_state = new_state

        def _mock_modify_trigger(disp, group, logargs, modifier,
                                 modify_state_reason=None, *args, **kwargs):
            self.assertEqual(disp, "disp")
            d = modifier(group, "state", *args, **kwargs)
            return d.addCallback(_set_new_state)

        self.mock_mt.side_effect = _mock_modify_trigger

        self.maybe_exec_policy = patch(
            self, 'otter.scheduler.maybe_execute_scaling_policy',
            return_value=defer.succeed('newstate'))
        self.log = mock_log()
        self.log_args = {
            'tenant_id': '1234',
            'scaling_group_id': 'scal44',
            'policy_id': 'pol44',
            "scheduled_time": "1970-01-01T00:00:00Z"
        }
        self.event = {
            'tenantId': '1234',
            'groupId': 'scal44',
            'policyId': 'pol44',
            'trigger': datetime(1970, 1, 1),
            'cron': '*',
            'bucket': 1,
            'version': 'v2'
        }

    def test_event_executed(self):
        """
        Event is executed successfully and appropriate logs logged.
        """
        del_pol_ids = set()
        d = execute_event("disp", self.mock_store, self.log, self.event,
                          del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.log.msg.assert_called_once_with(
            "sch-exec-pol", cloud_feed=True, **self.log_args)
        self.maybe_exec_policy.assert_called_once_with(
            matches(IsBoundWith(**self.log_args)), 'transaction-id',
            self.mock_group, "state",
            policy_id=self.event['policyId'], version=self.event['version'])
        self.assertTrue(self.mock_mt.called)
        self.assertEqual(self.new_state, 'newstate')
        self.assertEqual(len(del_pol_ids), 0)

    def test_deleted_group_event(self):
        """This event's group has been deleted.

        Its policyId is logged, and no attempt is made to execute it.
        """
        del_pol_ids = set()
        self.mock_mt.side_effect = \
            lambda *_, **__: defer.fail(NoSuchScalingGroupError(1, 2))

        d = execute_event("disp", self.mock_store, self.log, self.event,
                          del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(del_pol_ids, set(['pol44']))
        self.assertFalse(self.maybe_exec_policy.called)

    def test_deleted_policy_event(self):
        """This event's policy has been deleted.

        Its policyId is added to deleted_policy_ids, and no attempt is
        made to execute it.
        """
        del_pol_ids = set()
        self.mock_mt.side_effect = (
            lambda *_, **__: defer.fail(NoSuchPolicyError(1, 2, 3)))

        d = execute_event("disp", self.mock_store, self.log, self.event,
                          del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(del_pol_ids, set(['pol44']))
        self.assertFalse(self.maybe_exec_policy.called)

    def test_semantic_prob(self):
        """
        Policy execution causes semantic error like cooldowns not met.
        i.e. CannotExecutePolicyError is captured and logged.
        """
        del_pol_ids = set()
        self.maybe_exec_policy.return_value = defer.fail(
            CannotExecutePolicyError(*range(4)))

        d = execute_event("disp", self.mock_store, self.log, self.event,
                          del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(len(del_pol_ids), 0)
        self.log.msg.assert_called_with(
            "sch-cannot-exec", reason=CheckFailure(CannotExecutePolicyError),
            cloud_feed=True, **self.log_args)

    def test_unknown_error(self):
        """
        Unknown error occurs. It is logged and not propagated.
        """
        del_pol_ids = set()
        self.maybe_exec_policy.return_value = defer.fail(ValueError(4))

        d = execute_event("disp", self.mock_store, self.log, self.event,
                          del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(len(del_pol_ids), 0)
        self.log.err.assert_called_with(
            CheckFailure(ValueError), "sch-exec-pol-err", cloud_feed=True,
            **self.log_args)
