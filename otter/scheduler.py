"""
The OtterClock.  Because, while a broken clock is right twice a day, an OtterClock
is right all the time and is probably what caused your regular clock to get broken
in the first place.
"""

"""
TODO to get cron working
* A class to manage cron entry
    - take en entry and gives next date
* update schema and model API to store cron entry in scaling_schedule
* After executing event, if the event has cron then find next time and update it
"""

from datetime import datetime
from functools import partial
from croniter import croniter

from twisted.internet import defer
from twisted.application.internet import TimerService

from silverberg.lock import BasicLock, BusyLockError, with_lock

from otter.util.hashkey import generate_transaction_id
from otter.rest.application import get_store
from otter import controller
from otter.log import log as otter_log


class Recurrence(object):
    """
    Represents a recurrence either from cron entry or from any other format
    """

    def __init__(self, cron=None, start=None):
        if not cron:
            raise ValueError('no cron')
        self.croniter = croniter(cron, start_time=start or datetime.utcnow())

    def get_next_datetime(self):
        return self.croniter.get_next(ret_type=datetime)


class SchedulerService(TimerService):
    """
    Service to trigger scheduled events
    """

    def __init__(self, batchsize, interval, slv_client, clock=None):
        """
        Initializes the scheduler service with batch size and interval

        :param int batchsize: number of events to fetch on each iteration
        :param int interval: time between each iteration
        :param slv_client: a :class:`silverberg.client.CQLClient` or
                    :class:`silverberg.cluster.RoundRobinCassandraCluster` instance used to get lock
        :param clock: An instance of IReactorTime provider that defaults to reactor if not provided
        """
        from otter.models.cass import LOCK_TABLE_NAME
        self.lock = BasicLock(slv_client, LOCK_TABLE_NAME, 'schedule', max_retry=0)
        TimerService.__init__(self, interval, self.check_for_events, batchsize)
        self.clock = clock

    def check_for_events(self, batchsize):
        """
        Check for events in the database before the present time.

        :return: a deferred that fires with None
        """

        def check_for_more(events):
            if len(events) == batchsize:
                return _do_check()
            return None

        def _do_check():
            d = with_lock(self.lock, self.fetch_and_process, batchsize)
            d.addCallback(check_for_more)
            # Return if we do not get lock as other process might be processing current events
            d.addErrback(lambda f: f.trap(BusyLockError) and None)
            return d

        return _do_check()

    def fetch_and_process(self, batchsize):
        """
        Fetch the events to be processed and process them.
        Also delete/update after processing them

        :return: a deferred that fires with list of events processed
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

            # TODO: If any of the executions give NoSuchPolicyError,
            # delete it and do not update its trigger time

            d.addErrback(log.err)
            return d.addCallback(lambda _: events)

        def update_delete_events(events):
            """
            Update events with cron entry with next trigger time
            Delete other events
            """
            if not len(events):
                return events

            events_to_delete, events_to_update = list(), list()
            for event in events:
                if event['cron']:
                    event['trigger'] = Recurrence(cron=event['cron']).get_next_datetime()
                    events_to_update.append(event)
                else:
                    events_to_delete.append(event['policyId'])

            log.bind(num_policy_ids_deleting=len(events_to_delete)).msg('Deleting events')
            log.bind(num_policy_ids_updating=len(events_to_update)).msg('Updating events')
            d = get_store().update_delete_events(events_to_delete, events_to_update)

            return d.addCallback(lambda _: events)

        # utcnow because of cass serialization issues
        utcnow = datetime.utcnow()
        log = log.bind(utcnow=utcnow)
        log.msg('Checking for events')
        deferred = get_store().fetch_batch_of_events(utcnow, batchsize)
        deferred.addCallback(process_events)
        deferred.addCallback(update_delete_events)
        deferred.addErrback(log.err)
        return deferred

    def execute_event(self, log, event):
        """
        Execute a single event

        :param log: A bound log for logging

        :return: a deferred with the results of execution
        """
        log.msg('Executing policy', group_id=event['groupId'], policy_id=event['policyId'])
        group = get_store().get_scaling_group(log, event['tenantId'], event['groupId'])
        d = group.modify_state(partial(controller.maybe_execute_scaling_policy,
                                       log, generate_transaction_id(),
                                       policy_id=event['policyId']))
        return d
