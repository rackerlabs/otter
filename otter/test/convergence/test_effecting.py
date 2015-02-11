"""Tests for convergence effecting."""

from effect import Constant, Effect, parallel

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import implementer

from otter.convergence.effecting import steps_to_effect
from otter.convergence.steps import IStep


@implementer(IStep)
class _Steppy(object):
    def as_effect(self):
        return Effect(Constant(None))


class StepsToEffectTests(SynchronousTestCase):
    """Tests for :func:`steps_to_effect`"""
    def test_uses_step_request(self):
        """Steps are converted to requests."""
        steps = [_Steppy(), _Steppy()]
        expected_effects = [Effect(Constant(None))] * 2
        effect = steps_to_effect(steps)
        self.assertEqual(effect, parallel(expected_effects))
