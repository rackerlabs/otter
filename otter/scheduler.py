"""
The OtterClock.  Because, while a broken clock is right twice a day, an OtterClock
is right all the time and is probably what caused your regular clock to get broken
in the first place.
"""

from datetime import datetime
from functools import partial
from croniter import croniter

from twisted.internet import defer
from twisted.application.internet import TimerService

from otter.util.hashkey import generate_transaction_id
from otter.controller import maybe_execute_scaling_policy, CannotExecutePolicyError
from otter.log import log as otter_log
from otter.models.interface import NoSuchPolicyError, NoSuchScalingGroupError
from otter.util.deferredutils import ignore_and_log


class SchedulerService(TimerService):
    """
    Service to trigger scheduled events
    """

    def __init__(self, batchsize, interval, store, kz_client,
                 zk_partition_path, time_boundary, buckets, clock=None, threshold=60):
        """
        Initialize the scheduler service

        :param int batchsize: number of events to fetch on each iteration
        :param int interval: time between each iteration
        :param kz_client: `TxKazooClient` instance
        :param buckets: an iterable containing the buckets which contains scheduled events
        :param zk_partition_path: Partiton path used by kz_client to partition the buckets
        :param time_boundary: Time to wait for partition to become stable
        :param clock: An instance of IReactorTime provider that defaults to reactor if not provided
        """
        TimerService.__init__(self, interval, self.check_events, batchsize)
        self.store = store
        self.clock = clock
        self.kz_client = kz_client
        self.buckets = buckets
        self.zk_partition_path = zk_partition_path
        self.time_boundary = time_boundary
        self.kz_partition = None
        self.threshold = threshold
        self.log = otter_log.bind(system='otter.scheduler')

    def startService(self):
        """
        Start this service. This will start buckets partitioning
        """
        self.kz_partition = self.kz_client.SetPartitioner(
            self.zk_partition_path, set=set(self.buckets),
            time_boundary=self.time_boundary)
        TimerService.startService(self)

    def stopService(self):
        """
        Stop this service. This will release buckets partitions it holds
        """
        TimerService.stopService(self)
        if self.kz_partition.acquired:
            return self.kz_partition.finish()

    def health_check(self):
        """
        Checks if scheduler service is healthy by comparing oldest event w.r.t current
        time. If oldtest event is older than a threshold, then it is not healthy

        :return: Deferred that fires with tuple (Bool, `dict` of extra debug info)
        """
        if not self.kz_partition.acquired:
            # TODO: Until there is check added for not being allocted for long time
            # it is fine to assume service is not healthy when it is allocating since
            # allocating should happen only on deploy or network issues
            return defer.succeed((False, {'reason': 'Not acquired'}))

        def check_older_events(events):
            now = datetime.utcnow()
            old_events = []
            for event in events:
                if event and (now - event['trigger']).total_seconds() > self.threshold:
                    old_events.append(event)
            return (not bool(old_events), {'old_events': old_events,
                                           'buckets': list(self.kz_partition)})

        d = defer.gatherResults(
            [self.store.get_oldest_event(bucket) for bucket in self.kz_partition],
            consumeErrors=True)
        d.addCallback(check_older_events)
        return d

    def check_events(self, batchsize):
        """
        Check for events occurring now and earlier
        """
        if self.kz_partition.allocating:
            self.log.msg('Partition allocating')
            return
        if self.kz_partition.release:
            self.log.msg('Partition changed. Repartitioning')
            return self.kz_partition.release_set()
        if self.kz_partition.failed:
            self.log.msg('Partition failed. Starting new')
            self.kz_partition = self.kz_client.SetPartitioner(
                self.zk_partition_path, set=set(self.buckets),
                time_boundary=self.time_boundary)
            return
        if not self.kz_partition.acquired:
            self.log.err('Unknown state {}. This cannot happen. Starting new'.format(
                self.kz_partition.state))
            self.kz_partition.finish()
            self.kz_partition = self.kz_client.SetPartitioner(
                self.zk_partition_path, set=set(self.buckets),
                time_boundary=self.time_boundary)
            return

        buckets = list(self.kz_partition)
        utcnow = datetime.utcnow()
        log = self.log.bind(scheduler_run_id=generate_transaction_id(), utcnow=utcnow)
        # TODO: This log might feel like spam since it'll occur on every tick. But
        # it'll be useful to debug partitioning problems (at least in initial deployment)
        log.msg('Got buckets {buckets}', buckets=buckets)

        return defer.gatherResults(
            [check_events_in_bucket(
                log, self.store, bucket, utcnow, batchsize) for bucket in buckets])


def check_events_in_bucket(log, store, bucket, now, batchsize):
    """
    Retrieves events in the given bucket that occur before or at now,
    in batches of batchsize, for processing

    :param log: A bound log for logging
    :param store: `IScalingGroupCollection` provider
    :param bucket: Bucket to check events in
    :param now: Time before which events are checked
    :param batchsize: Number of events to check at a time

    :return: a deferred that fires with None
    """

    log = log.bind(bucket=bucket)

    def check_for_more(num_events):
        if num_events == batchsize:
            return _do_check()

    def _do_check():
        d = store.fetch_and_delete(bucket, now, batchsize)
        d.addCallback(process_events, store, log)
        d.addCallback(check_for_more)
        d.addErrback(log.err)
        return d

    return _do_check()


def process_events(events, store, log):
    """
    Executes all the events and adds the next occurrence of each event to the buckets

    :param events: list of event dict to process
    :param store: `IScalingGroupCollection` provider
    :param log: A bound log for logging

    :return: a `Deferred` that fires with number of events processed
    """
    if not events:
        return 0

    log.msg('Processing {num_events} events', num_events=len(events))

    deleted_policy_ids = set()

    deferreds = [
        execute_event(store, log, event, deleted_policy_ids)
        for event in events
    ]
    d = defer.gatherResults(deferreds, consumeErrors=True)
    d.addCallback(lambda _: add_cron_events(store, log, events, deleted_policy_ids))
    return d.addCallback(lambda _: len(events))


def next_cron_occurrence(cron):
    """
    Return next occurence of given cron entry
    """
    return croniter(cron, start_time=datetime.utcnow()).get_next(ret_type=datetime)


def add_cron_events(store, log, events, deleted_policy_ids):
    """
    Update events with cron entry with next trigger time.

    :param store: `IScalingGroupCollection` provider
    :param log: A bound log for logging
    :param events: list of event dict whose next event has to be added
    :param deleted_policy_ids: set of policy ids that have been deleted. Events
                               corresponding to these policy ids will not be added

    :return: `Deferred` that fires will result of adding cron events or None if no
             events have to be added
    """
    if not events:
        return

    new_cron_events = []
    for event in events:
        if event['cron'] and event['policyId'] not in deleted_policy_ids:
            event['trigger'] = next_cron_occurrence(event['cron'])
            new_cron_events.append(event)

    if new_cron_events:
        log.msg('Adding {new_cron_events} cron events', new_cron_events=len(new_cron_events))
        return store.add_cron_events(new_cron_events)


def execute_event(store, log, event, deleted_policy_ids):
    """
    Execute a single event

    :param store: `IScalingGroupCollection` provider
    :param log: A bound log for logging
    :param event: event dict to execute
    :param deleted_policy_ids: Set of policy ids that are deleted. Policy id will be added
                               to this if its scaling group or policy has been deleted
    :return: a deferred with None. Any error occurred during execution is logged
    """
    tenant_id, group_id, policy_id = event['tenantId'], event['groupId'], event['policyId']
    log = log.bind(tenant_id=tenant_id, scaling_group_id=group_id, policy_id=policy_id)
    log.msg('Scheduler executing policy {policy_id}')
    group = store.get_scaling_group(log, tenant_id, group_id)
    d = group.modify_state(partial(maybe_execute_scaling_policy,
                                   log, generate_transaction_id(),
                                   policy_id=policy_id, version=event['version']))
    d.addErrback(ignore_and_log, CannotExecutePolicyError,
                 log, 'Scheduler cannot execute policy {policy_id}')

    def collect_deleted_policy(failure):
        failure.trap(NoSuchScalingGroupError, NoSuchPolicyError)
        deleted_policy_ids.add(policy_id)

    d.addErrback(collect_deleted_policy)
    d.addErrback(log.err, 'Scheduler failed to execute policy {policy_id}')
    return d
