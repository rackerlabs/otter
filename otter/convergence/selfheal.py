"""
Self heal service
"""

from toolz.curried import filter

from twisted.application.service import MultiService

from txeffect import perform

from otter.convergence.service import trigger_convergence


class SelfHeal(MultiService, object):
    """
    A service that triggers convergence on all the groups on interval basis.
    Only one node is allowed to do this.
    """

    def __init__(self, dispatcher, kz_client, interval, log, clock,
                 config_func):
        super(SelfHeal, self).__init__()
        self.disp = dispatcher
        self.log = log
        self.lock = self.kz_client.Lock("/selfheallock")
        self.lock_acquired = False
        self.clock = clock
        self.time_range = interval - 5
        self.config_func = config_func
        timer = TimerService(interval, self._converge_all)
        timer.clock = clock
        timer.setServiceParent(self)

    def stopService(self):
        # We explicitly do not wait for convergence triggering to complete
        # before shutting down the service. We however want to release the lock
        # before shutting down
        super(SelfHeal, self).stopService()
        if self.lock_acquired:
            return self.lock.release()

    def health_check(self):
        """
        Return about whether this object has lock
        """
        return True, {"has_lock": self.lock_acquired}

    def _perform(self):
        d = perform(self.disp, get_groups_to_converges(self.config_func))
        d.addCallback(self._setup_converges)
        return d.addErrback(self.log.err, "self-heal-err")

    def _setup_converges(self, groups):
        wait_time = self.time_range / len(groups)
        for i, group in enumerate(groups):
            self.clock.callLater(
                i * wait_time, perform, self.disp,
                check_and_trigger(group["tenantId"], group["groupId"]))

    @inlineCallbacks
    def _converge_all(self):
        if self.lock_acquired:
            yield self._perform()
        else:
            if (yield self.lock.acquire(False, None)):
                self.log.msg("self-heal-lock-acquired")
                self.lock_acquired = True
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
