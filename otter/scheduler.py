"""
The OtterClock.  Because, while a broken clock is right twice a day, an OtterClock
is right all the time and is probably what caused your regular clock to get broken
in the first place.
"""

from datetime import datetime
from functools import partial

from twisted.internet import defer
from twisted.application.internet import TimerService

from otter.util.hashkey import generate_transaction_id
from otter.rest.application import get_store
from otter import controller
from otter.log import log as otter_log


class SchedulerService(TimerService):
    """
    Service to trigger scheduled events
    """

    def __init__(self, batchsize, interval, clock=None):
        """
        Initializes the scheduler service with batch size and interval

        :param int batchsize: number of events to fetch on each iteration
        :param int interval: time between each iteration
        :param clock: An instance of IReactorTime provider that defaults to reactor if not provided
        """
        TimerService.__init__(self, interval, self.check_for_events, batchsize)
        self.clock = clock

    def check_for_events(self, batchsize):
        """
        Check for events in the database before the present time.

        :return: a deferred that fires with None
        """
        log = otter_log.bind(scheduler_run_id=generate_transaction_id())

        def process_events(events):

            if not len(events):
                return events

            log.msg('Processing events', num_events=len(events))
            deferreds = [
                self.execute_event(log, event) for event in events
            ]
            d = defer.gatherResults(deferreds, consumeErrors=True)

            d.addErrback(log.err)
            d.addCallback(lambda _: events)

            return d

        def check_for_more(events):
            if len(events) == batchsize:
                return self.check_for_events(batchsize)
            return None

        def delete_events(events):
            if len(events) != 0:
                policy_ids = [event[2] for event in events]
                log.bind(num_policy_ids=len(policy_ids)).msg('Deleting events')
                get_store().delete_events(policy_ids)
            return events

        # utcnow because of cass serialization issues
        utcnow = datetime.utcnow()
        log = log.bind(utcnow=utcnow)
        log.msg('Checking for events')
        deferred = get_store().fetch_batch_of_events(utcnow, batchsize)
        deferred.addCallback(process_events)
        deferred.addCallback(delete_events)
        deferred.addCallback(check_for_more)
        deferred.addErrback(log.err)
        return deferred

    def execute_event(self, log, event):
        """
        Execute a single event

        :param log: A bound log for logging

        :return: a deferred with the results of execution
        """
        tenant_id, group_id, policy_id, trigger = event
        log.msg('Executing policy', group_id=group_id, policy_id=policy_id)
        group = get_store().get_scaling_group(log, tenant_id, group_id)
        d = group.modify_state(partial(controller.maybe_execute_scaling_policy,
                                       log, generate_transaction_id(),
                                       policy_id=policy_id))
        return d
