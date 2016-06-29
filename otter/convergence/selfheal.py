"""
Self heal service. It continously triggers convergence on all groups by equally
distributing the triggering over a period of time in effect "heal"ing the
groups.
"""

from effect import ComposedDispatcher, Effect, TypeDispatcher
from effect.do import do, do_return

from kazoo.exceptions import LockTimeout

from toolz.curried import filter

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import deferred_performer, perform

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import trigger_convergence
from otter.log.intents import with_log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import ScalingGroupStatus
from otter.util.zk import AcquireLock, GetChildren


class SelfHeal(MultiService, object):
    """
    A service that triggers convergence on all the groups on interval basis.
    Only one node is allowed to do this.

    :ivar disp: Effect dispatcher to perform all effects (ZK, CASS, log, etc)
    :type disp: Either :obj:`ComposedDispatcher` or :obj:`TypeDispatcher`

    :ivar log: Twisted logger with .msg and .err methods
    :ivar lock: Lock object from :obj:`TxKazooClient`
    :ivar :obj:`TxKazooClient` kz_client: Twistified kazoo client object
    :ivar :obj:`IReactorTime` clock: Reactor providing timing APIs
    :ivar ``list`` calls: List of `IDelayedCall` objects. Each object
        represents scheduled call to trigger convergence on a group
    """

    def __init__(self, dispatcher, kz_client, interval, log, clock,
                 config_func):
        """
        :var float interval: All groups will be scheduled to be triggered
            within this time
        :var callable config_func: Callable used when calling
            :func:`tenant_is_enabled`
        """
        super(SelfHeal, self).__init__()
        self.disp = dispatcher
        self.log = log.bind(otter_service="selfheal")
        self.lock = kz_client.Lock("/selfheallock")
        self.kz_client = kz_client
        self.clock = clock
        self.calls = []
        timer = TimerService(
            interval,
            lambda: self._setup_if_locked(config_func, interval).addErrback(
                self.log.err, "self-heal-setup-err"))
        timer.clock = clock
        timer.setServiceParent(self)

    def stopService(self):
        """
        Stop service by cancelling any remaining scheduled calls and releasing
        the lock
        """
        super(SelfHeal, self).stopService()
        self._cancel_scheduled_calls()
        return self.lock.release()

    def _cancel_scheduled_calls(self):
        """
        Cancel any remaining scheduled calls.

        :return: Number of remaining active scheduled calls before cancelling
        """
        active = 0
        for call in self.calls:
            if call.active():
                active += 1
                call.cancel()
        self.calls = []
        return active

    def health_check(self):
        """
        Return about whether this object has lock
        """
        d = perform(self.disp, is_lock_acquired(self.lock))
        return d.addCallback(lambda b: (True, {"has_lock": b}))

    @inlineCallbacks
    def _setup_convergences(self, config_func, time_range):
        """
        Get groups to converge and setup scheduled calls to trigger convergence
        on each of them within time_range. For parameters, see
        :func:`__init__` docs.
        """
        groups = yield perform(self.disp,
                               get_groups_to_converge(config_func))
        active = self._cancel_scheduled_calls()
        if active:
            # This should never happen
            self.log.err(RuntimeError("self-heal-calls-err"),
                         "self-heal-calls-err", active=active)
        if not groups:
            returnValue(None)
        wait_time = float(time_range) / len(groups)
        for i, group in enumerate(groups):
            self.calls.append(
                self.clock.callLater(
                    i * wait_time, perform, self.disp,
                    check_and_trigger(group["tenantId"], group["groupId"]))
            )

    def _setup_if_locked(self, config_func, time_range):
        """
        Setup convergence triggering on all groups by acquiring the lock and
        calling ``_setup_convergences``. For parameters, see
        :func:`__init__` docs.
        """
        class SetupConvergences(object):
            pass

        @deferred_performer
        def sc_performer(d, i):
            return self._setup_convergences(config_func, time_range)

        dispatcher = ComposedDispatcher([
            TypeDispatcher({SetupConvergences: sc_performer}), self.disp])

        d = perform(
            dispatcher,
            call_if_acquired(self.lock, Effect(SetupConvergences())))
        return d.addCallback(
            lambda b: self.log.msg("self-heal-lock-acquired") if b else None)


@do
def call_if_acquired(lock, eff):
    """
    Call ``eff`` if ``lock`` is acquired. If not, try to acquire the lock
    and call ``eff``. This function is different from
    :func:`otter.util.deferredutils.with_lock` where this does not release
    the lock after calling ``func``. Also it expects that lock may already be
    acquired.

    :param lock: Lock object from :obj:`TxKazooClient`
    :param eff: ``Effect`` to call if/when lock is acquired

    :return: True if lock was acquired by this function, False otherwise
    :rtype: ``Effect`` of ``bool``
    """
    if (yield is_lock_acquired(lock)):
        yield eff
    else:
        try:
            yield Effect(AcquireLock(lock, True, 0.1))
            yield eff
            yield do_return(True)
        except LockTimeout:
            # expected. Nothing to do here.
            pass
    yield do_return(False)


def get_groups_to_converge(config_func):
    """
    Get all tenant's all groups that needs convergence triggering
    """
    eff = Effect(GetAllValidGroups())
    eff = eff.on(
        filter(lambda g: tenant_is_enabled(g["tenantId"], config_func)))
    return eff.on(list)


@do
def check_and_trigger(tenant_id, group_id):
    """
    Trigger convergence on given group if it is ACTIVE and not paused
    """
    group, info = yield Effect(
        GetScalingGroupInfo(tenant_id=tenant_id, group_id=group_id))
    state = info["state"]

    if state.status == ScalingGroupStatus.ACTIVE and (not state.paused):
        yield with_log(
            trigger_convergence(tenant_id, group_id),
            tenant_id=tenant_id, scaling_group_id=group_id)


@do
def is_lock_acquired(lock):
    """
    Is the given lock object currently acquired by this worker?

    :return: `Effect` of `bool`
    """
    children = yield Effect(GetChildren(lock.path))
    if not children:
        yield do_return(False)
    # The last 10 characters are sequence number as per
    # https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html\
    # #Sequence+Nodes+--+Unique+Naming
    yield do_return(
        sorted(children, key=lambda c: c[-10:])[0][:-10] == lock.prefix)
