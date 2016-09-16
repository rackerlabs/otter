"""
Self heal service. It continously triggers convergence on all groups by equally
distributing the triggering over a period of time in effect "heal"ing the
groups.
"""

from effect import ComposedDispatcher, Effect, TypeDispatcher
from effect.do import do, do_return

from toolz.curried import filter

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue

from txeffect import deferred_performer, perform

from zope.interface import implementer

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import trigger_convergence
from otter import lockedtimerservice as lts
from otter.log.intents import msg, with_log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import NoSuchScalingGroupError, ScalingGroupStatus


@implementer(lts.ILockedTimerFunc)
class SelfHeal(object):
    """
    A service that triggers convergence on all the groups on interval basis.
    Only one node is allowed to do this.

    :ivar disp: Effect dispatcher to perform all effects (ZK, CASS, log, etc)
    :type disp: Either :obj:`ComposedDispatcher` or :obj:`TypeDispatcher`

    :ivar log: Twisted logger with .msg and .err methods
    :ivar lock: Lock object from :obj:`TxKazooClient`
    :ivar TxKazooClient kz_client: Twistified kazoo client object
    :ivar IReactorTime clock: Reactor providing timing APIs
    :ivar list calls: List of `IDelayedCall` objects. Each object
        represents scheduled call to trigger convergence on a group
    """

    name = "selfheal"

    def __init__(self, clock, dispatcher, config_func, time_range, log):
        """
        :var float interval: All groups will be scheduled to be triggered
            within this time
        :var callable config_func: Callable used when calling
            :func:`tenant_is_enabled`
        :var lock: lock object used primarily for testing. If not given, a new
            lock will be created from ``zk.PollingLock``
        """
        self.clock = clock
        self.dispatcher = dispatcher
        self.config_func = config_func
        self.time_range = time_range
        self.log = log.bind(otter_service=self.name)
        self.calls = []

    def call(self):
        """
        Setup convergencence triggerring and capture any error occurred
        """
        d = self._setup_convergences()
        return d.addErrback(self.log.err, "selfheal-setup-err")

    def stop(self):
        """
        Stop by cancel any remaining scheduled calls
        """
        self._cancel_scheduled_calls()

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

    @inlineCallbacks
    def _setup_convergences(self):
        """
        Get groups to converge and setup scheduled calls to trigger convergence
        on each of them within time_range.
        """
        groups = yield perform(self.disp,
                               get_groups_to_converge(self.config_func))
        active = self._cancel_scheduled_calls()
        if active:
            # This should never happen
            self.log.err(RuntimeError("selfheal-calls-err"),
                         "selfheal-calls-err", active=active)
        if not groups:
            returnValue(None)
        wait_time = float(self.time_range) / len(groups)
        for i, group in enumerate(groups):
            self.calls.append(
                self.clock.callLater(
                    i * wait_time, perform, self.disp,
                    check_and_trigger(group["tenantId"], group["groupId"]))
            )


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
    try:
        group, info = yield Effect(
            GetScalingGroupInfo(tenant_id=tenant_id, group_id=group_id))
    except NoSuchScalingGroupError:
        # Nothing to do if group has been deleted
        yield msg("selfheal-group-deleted",
                  tenant_id=tenant_id, scaling_group_id=group_id)
    else:
        state = info["state"]
        if state.status == ScalingGroupStatus.ACTIVE and (not state.paused):
            yield with_log(
                trigger_convergence(tenant_id, group_id),
                tenant_id=tenant_id, scaling_group_id=group_id)
