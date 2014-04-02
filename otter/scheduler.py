"""
The OtterClock.  Because, while a broken clock is right twice a day, an OtterClock
is right all the time and is probably what caused your regular clock to get broken
in the first place.
"""

from datetime import datetime
from functools import partial
import json

from croniter import croniter

from twisted.internet import defer
from twisted.application.service import Service
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineOnlyReceiver
from twisted.internet.endpoints import ProcessEndpoint
from twisted.python import procutils

from otter.util.hashkey import generate_transaction_id
from otter.controller import maybe_execute_scaling_policy, CannotExecutePolicyError
from otter.log import log as otter_log
from otter.models.interface import NoSuchPolicyError, NoSuchScalingGroupError
from otter.util.deferredutils import ignore_and_log


class PartitionProtocol(LineOnlyReceiver):
    """
    Handle getting buckets from partition process
    """
    def __init__(self, scheduler):
        self.delimiter = '\n'
        self.scheduler = scheduler
        self.ignore = False

    def connectionMade(self):
        # TODO: Temporary HACK! since ProcessTransport does not have disconnecting attr
        # https://twistedmatrix.com/trac/ticket/6606
        self.transport.disconnecting = False

    def lineReceived(self, line):
        if not self.transport.disconnecting and not self.ignore:
            body = json.loads(line)
            self.scheduler.set_buckets(map(int, body['buckets']))

    def connectionLost(self, reason):
        if not self.transport.disconnecting and not self.ignore:
            self.scheduler.process_stopped(reason)

    def disconnect(self):
        # Ideally, need not explicitly set this but doing this since ProcessTransport
        # does not have disconnecting attr
        self.transport.disconnecting = True
        self.transport.loseConnection()


class SchedulerService(Service):
    """
    Service to trigger scheduled events
    """

    def __init__(self, batchsize, interval, store, zk_hosts,
                 zk_partition_path, time_boundary, buckets, reactor,
                 kz_handler, part_script_path, clock=None, threshold=60):
        """
        Initialize the scheduler service

        :param int batchsize: number of events to fetch on each iteration
        :param int interval: time between each iteration
        :param kz_hosts: Zookeeper hosts
        :param buckets: an iterable containing the buckets which contains scheduled events
        :param zk_partition_path: Partiton path used by kz_client to partition the buckets
        :param time_boundary: Time to wait for partition to become stable
        :param reactor: An instance of IReactorProcess provider that defaults to reactor if not provided
        :param kz_handler: One of "thread" or "gevent" describing the handler used by subprocess
        :param clock: An instance of IReactorTime provider that defaults to reactor param
        """
        self.store = store
        self.reactor = reactor
        self.batchsize = batchsize
        self.interval = interval
        self.clock = clock or self.reactor
        self.last_acquired_seconds = 0

        self.buckets = buckets
        self.buckets_acquired = None
        self.zk_hosts = zk_hosts
        self.zk_partition_path = zk_partition_path
        self.kz_handler = kz_handler
        self.time_boundary = time_boundary
        self.proc_protocol = None
        self.threshold = threshold
        self.partition_py_path = part_script_path

        # TODO: This should probably come from env/config
        self.python_exe = procutils.which('python')

        self.log = otter_log.bind(system='otter.scheduler')

    def startService(self):
        """
        Start this service. This will start buckets partitioning
        """
        Service.startService(self)
        return self.start_process()

    def start_process(self):
        """
        Start the subprocess that does the partitioning
        """
        pe = ProcessEndpoint(
            self.reactor, self.python_exe,
            args=[self.python_exe, self.partition_py_path, self.kz_handler, self.zk_hosts,
                  self.zk_partition_path, ','.join(map(str, self.buckets)),
                  str(self.time_boundary), str(self.interval)],
            env=None)
        d = pe.connect(ClientFactory.forProtocol(lambda: PartitionProtocol(self)))
        d.addCallback(partial(setattr, self, 'proc_protocol'))
        d.addErrback(self.log.err, 'Could not run partition process')
        return d

    def process_stopped(self, reason):
        """
        Called when partition subprocess is stopped
        """
        # Start the process again only if service is still running as this method will
        # get called when service is in process of shutting down
        if self.running:
            self.log.err(reason, 'Process unexpectedly stopped')
            self.start_process()

    def stopService(self):
        """
        Stop this service. This will stop the partitioning subprocess
        """
        Service.stopService(self)
        return self.stop_process()

    def stop_process(self):
        """
        Stop subprocess that does partitioning
        """
        if self.proc_protocol:
            self.proc_protocol.disconnect()
            self.proc_protocol = None

    def reset(self, new_partition_path):
        """
        Reset the scheduler with new partition path
        """
        # TODO: Collect the old protocol and check if there are too many hanging around
        # instead of blindly ignoring them
        # Only ignore the currently running process. Do not stop it, let it run
        if self.proc_protocol:
            self.proc_protocol.ignore = True
            self.proc_protocol = None
        # Set new path and start new process
        self.zk_partition_path = new_partition_path
        self.start_process()

    def health_check(self):
        """
        Checks if scheduler service is healthy by comparing oldest event w.r.t current
        time. If oldtest event is older than a threshold, then it is not healthy

        :return: Deferred that fires with tuple (Bool, `dict` of extra debug info)
        """
        if not self.buckets_acquired:
            # TODO: Until there is check added for not being allocted for long time
            # it is fine to assume service is not healthy when it is allocating since
            # allocating should happen only on deploy or network issues
            return defer.succeed((False, {'reason': 'Not acquired'}))

        idle_time = self.clock.seconds() - self.last_acquired_seconds
        if idle_time >= self.threshold:
            return defer.succeed(
                (False, {'reason': 'No bucket updates for {} seconds'.format(idle_time)}))

        def check_older_events(events):
            now = datetime.utcnow()
            old_events = []
            for event in events:
                if event and (now - event['trigger']).total_seconds() > self.threshold:
                    event['version'] = str(event['version'])
                    event['trigger'] = str(event['trigger'])
                    old_events.append(event)
            return (not bool(old_events), {'old_events': old_events,
                                           'buckets': self.buckets_acquired})

        d = defer.gatherResults(
            [self.store.get_oldest_event(bucket) for bucket in self.buckets_acquired],
            consumeErrors=True)
        d.addCallback(check_older_events)
        return d

    def set_buckets(self, buckets):
        """
        Set buckets acquired for this scheduler
        """
        self.buckets_acquired = buckets
        self.last_acquired_seconds = self.clock.seconds()
        self.check_events()

    def check_events(self):
        """
        Check for events occurring now and earlier
        """
        if not self.buckets_acquired:
            self.log.msg('No buckets')
            return

        utcnow = datetime.utcnow()
        log = self.log.bind(scheduler_run_id=generate_transaction_id(), utcnow=utcnow)
        # TODO: This log might feel like spam since it'll occur on every tick. But
        # it'll be useful to debug partitioning problems (at least in initial deployment)
        log.msg('Got buckets {buckets}', buckets=self.buckets_acquired)

        return defer.gatherResults(
            [check_events_in_bucket(log, self.store, bucket, utcnow, self.batchsize)
             for bucket in self.buckets_acquired])


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
