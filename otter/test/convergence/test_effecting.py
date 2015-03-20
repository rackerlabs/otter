"""Tests for convergence effecting."""

from effect import Constant, Effect, Error, ParallelEffects, sync_perform

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import implementer

from otter.convergence.effecting import steps_to_effect
from otter.convergence.model import StepResult
from otter.convergence.steps import IStep
from otter.test.utils import test_dispatcher, transform_eq


@implementer(IStep)
class _Steppy(object):
    def __init__(self, effect):
        self.effect = effect

    def as_effect(self):
        return self.effect


class StepsToEffectTests(SynchronousTestCase):
    """Tests for :func:`steps_to_effect`"""
    def test_uses_step_request(self):
        """Steps are converted to requests."""
        steps = [_Steppy(Effect(Constant((StepResult.SUCCESS, 'foo')))),
                 _Steppy(Effect(Error(RuntimeError('uh oh'))))]
        effect = steps_to_effect(steps)
        self.assertIs(type(effect.intent), ParallelEffects)
        self.assertEqual(
            sync_perform(test_dispatcher(), effect),
            [(StepResult.SUCCESS, 'foo'),
             (StepResult.RETRY, [transform_eq(lambda e: (type(e), e.args),
                                              (RuntimeError, ('uh oh',)))])])
