"""
The OtterClock.  Because, while a broken clock is right twice a day, an OtterClock
is right all the time and is probably what caused your regular clock to get broken
in the first place.
"""
from otter.rest.application import get_store
from datetime import datetime
from functools import partial
from twisted.internet import defer, reactor, task
from otter.util.hashkey import generate_transaction_id
from otter import controller


def execute_event(log, event):
    """
    Execute a single event

    :param log: A bound log for logging

    :return: a deferred with the results of execution
    """
    group = get_store().get_scaling_group(log, event[0], event[1])
    d = group.modify_state(partial(controller.maybe_execute_scaling_policy,
                                   log, generate_transaction_id(),
                                   policy_id=event[2]))
    return d


def check_for_events(log, batchsize, iclock=None):
    """
    Check for events in the database before the present time.

    :param log: A bound log for logging

    :return: a deferred that fires with None
    """
    if iclock is None:
        iclock = reactor

    def process_events(events):
        deferreds = [
            execute_event(log, event) for event in events
        ]
        d = defer.gatherResults(deferreds, consumeErrors=True)
        d.addCallback(lambda _: events)
        return d

    def check_for_more(events):
        if len(events) == batchsize:
            return task.deferLater(iclock, 0, check_for_events, log, batchsize, iclock)
        return None

    def delete_events(events):
        if len(events) != 0:
            policy_ids = [event[2] for event in events]
            get_store().delete_events(policy_ids)
        return events

    # utcnow because of cass serialization issues
    deferred = get_store().fetch_batch_of_events(datetime.utcnow(), batchsize)
    deferred.addCallback(process_events)
    deferred.addCallback(delete_events)
    # DELETE EVENTS HERE
    deferred.addCallback(check_for_more)
    return deferred
