"""
Self heal service
"""

from effect import Effect
from effect.do import do, do_return

from kazoo.protocol.states import KazooState

from toolz.curried import filter

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import perform

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import trigger_convergence
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.util.zk import GetChildren


class SelfHeal(MultiService, object):
    """
    A service that triggers convergence on all the groups on interval basis.
    Only one node is allowed to do this.
    """

    def __init__(self, dispatcher, kz_client, interval, log, clock,
                 config_func):
        super(SelfHeal, self).__init__()
        self.disp = dispatcher
        self.log = log.bind(otter_service="selfheal")
        self.lock = kz_client.Lock("/selfheallock")
        self.kz_client = kz_client
        self.clock = clock
        self.time_range = interval - 5
        self.config_func = config_func
        self.calls = []
        timer = TimerService(interval, self._converge_all)
        timer.clock = clock
        timer.setServiceParent(self)

    def stopService(self):
        super(SelfHeal, self).stopService()
        self._cancel_scheduled_calls()
        return self.lock.release()

    def _cancel_scheduled_calls(self):
        """
        Cancel any remaining scheduled calls
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
        d = lock_is_acquired(self.disp, self.lock)
        return d.addCallback(lambda b: (True, {"has_lock": b}))

    def _perform(self):
        d = perform(self.disp, get_groups_to_converge(self.config_func))
        d.addCallback(self._setup_converges)
        return d.addErrback(self.log.err, "self-heal-err")

    def _setup_converges(self, groups):
        active = self._cancel_scheduled_calls()
        if active:
            # This should never happen
            self.log.err(RuntimeError("self-heal-calls-err"),
                         "self-heal-calls-err", active=active)
        wait_time = float(self.time_range) / len(groups)
        for i, group in enumerate(groups):
            self.calls.append(
                self.clock.callLater(
                    i * wait_time, perform, self.disp,
                    check_and_trigger(group["tenantId"], group["groupId"]))
            )

    @inlineCallbacks
    def _converge_all(self):
        if self.kz_client.state != KazooState.CONNECTED:
            self.log.err(RuntimeError("self-heal-kz-state"),
                         "self-heal-kz-state", state=self.kz_client.state)
            returnValue(None)
        if (yield lock_is_acquired(self.lock)):
            yield self._perform()
        else:
            if (yield self.lock.acquire(False, None)):
                self.log.msg("self-heal-lock-acquired")
                yield self._perform()


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
    group_info = yield Effect(
        GetScalingGroupInfo(tenant_id=tenant_id, group_id=group_id))
    state = group_info["state"]

    if (state["status"] == "ACTIVE") and (not state["paused"]):
        yield trigger_convergence(tenant_id, group_id)


def lock_is_acquired(dispatcher, lock):
    """
    Does given lock object has the lock?

    :return: `Deferred` of `bool`
    """
    return perform(dispatcher, lock_is_acquired_eff(lock))


def lock_is_acquired_eff(lock):
    """
    Does given lock object has the lock?

    :return: `Effect` of `bool`
    """
    children = yield Effect(GetChildren(lock.path))
    if not children:
        yield do_return(False)
    # The last 10 characters are sequence number as per
    # https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html\
    # #Sequence+Nodes+--+Unique+Naming
    yield do_return(sorted(children, key=lambda c: c[-10:])[0] == lock.node)
