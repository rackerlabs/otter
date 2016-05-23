"""
Self heal service.
"""

from effect import Effect
from effect.do import do, do_return

from kazoo.exceptions import LockTimeout
from kazoo.protocol.states import KazooState

from toolz.curried import filter

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import perform

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import trigger_convergence
from otter.log.intents import with_log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import ScalingGroupStatus
from otter.util.zk import GetChildren


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
            lambda: self._converge_all(config_func, interval).addErrback(
                self.log.err, "self-heal-convergeall-err"))
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
        d = is_lock_acquired(self.disp, self.lock)
        return d.addCallback(lambda b: (True, {"has_lock": b}))

    @inlineCallbacks
    def _perform(self, config_func, time_range):
        """
        Get groups to converge and setup scheduled calls to trigger convergence
        on each of them within time_range
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

    @inlineCallbacks
    def _converge_all(self, config_func, time_range):
        """
        Setup convergence triggering on all groups by acquiring the lock and
        calling _perform
        """
        if self.kz_client.state != KazooState.CONNECTED:
            self.log.err(RuntimeError("self-heal-kz-state"),
                         "self-heal-kz-state", state=self.kz_client.state)
            returnValue(None)
        # The reason why it checks everytime by talking to ZK is because
        # we could've lost the lock if there where connection changes between
        # subsequent intervals and it is not clear how state change to
        # SUSPENDED should be handled
        if (yield is_lock_acquired(self.disp, self.lock)):
            yield self._perform(config_func, time_range)
        else:
            try:
                yield self.lock.acquire(True, 0.1)
                self.log.msg("self-heal-lock-acquired")
                yield self._perform(config_func, time_range)
            except LockTimeout:
                # expected. Nothing to do here. Will try on next interval
                pass


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


def is_lock_acquired(dispatcher, lock):
    """
    Does given lock object has acquired the lock? It does this by getting
    all the children and checking if first ephemeral node is ours

    :return: `Deferred` of `bool`
    """
    return perform(dispatcher, is_lock_acquired_eff(lock))


@do
def is_lock_acquired_eff(lock):
    """
    Does given lock object has acquired the lock?

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
