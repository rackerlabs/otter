"""
Self heal service. It continously triggers convergence on all groups by equally
distributing the triggering over a period of time in effect "heal"ing the
groups.
"""

import attr

from effect import ComposedDispatcher, Effect, TypeDispatcher
from effect.do import do, do_return

from toolz.curried import filter

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.interfaces import IReactorTime

from txeffect import deferred_performer, perform

from zope.interface import implementer

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import trigger_convergence
from otter import lockedtimerservice as lts
from otter.log import BoundLog
from otter.log.intents import msg, with_log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import NoSuchScalingGroupError, ScalingGroupStatus


@implementer(lts.ILockedTimerFunc)
@attr.s
class SelfHeal(object):
    """
    A class that triggers convergence on all the groups over a time range when
    its ``call`` method is called

    :ivar clock: Reactor providing timing APIs
    :vartype: :obj:`IReactorTime`
    :ivar dispatcher: Effect dispatcher to perform all effects
        (ZK, CASS, log, etc)
    :vartype dispatcher: Either :obj:`ComposedDispatcher` or
        :obj:`TypeDispatcher`
    :ivar callable config_func: Callable used when calling
        :func:`tenant_is_enabled`
    :ivar float time_range: Seconds over which convergence triggerring will be
        spread evenly
    :ivar log: :obj:`BoundLog` object used to log messages
    :ivar list _calls: List of :obj:`IDelayedCall` objects. Each object
        represents scheduled call to trigger convergence on a group
    """

    name = "selfheal"
    clock = attr.ib(validator=attr.validators.provides(IReactorTime))
    dispatcher = attr.ib(
        validator=attr.validators.instance_of((ComposedDispatcher,
                                               TypeDispatcher)))
    config_func = attr.ib()
    time_range = attr.ib(validator=attr.validators.instance_of(float))
    log = attr.ib(
        validator=attr.validators.instance_of(BoundLog),
        convert=lambda l: l.bind(otter_service=SelfHeal.name))
    _calls = attr.ib(default=attr.Factory(list))

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
        for call in self._calls:
            if call.active():
                active += 1
                call.cancel()
        self._calls = []
        return active

    @inlineCallbacks
    def _setup_convergences(self):
        """
        Get groups to converge and setup scheduled calls to trigger convergence
        on each of them within time_range.
        """
        groups = yield perform(self.dispatcher,
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
            self._calls.append(
                self.clock.callLater(
                    i * wait_time, perform, self.dispatcher,
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
