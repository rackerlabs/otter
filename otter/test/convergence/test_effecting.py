"""Tests for convergence effecting."""

from effect import Constant, Effect, Error, ParallelEffects, sync_perform

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.effecting import steps_to_effect
from otter.convergence.model import StepResult
from otter.test.utils import TestStep, test_dispatcher, transform_eq


class StepsToEffectTests(SynchronousTestCase):
    """Tests for :func:`steps_to_effect`"""
    def test_uses_step_request(self):
        """Steps are converted to requests."""
        steps = [TestStep(Effect(Constant((StepResult.SUCCESS, 'foo')))),
                 TestStep(Effect(Error(RuntimeError('uh oh'))))]
        effect = steps_to_effect(steps)
        self.assertIs(type(effect.intent), ParallelEffects)
        self.assertEqual(
            sync_perform(test_dispatcher(), effect),
            [(StepResult.SUCCESS, 'foo'),
             (StepResult.RETRY, [transform_eq(lambda e: (type(e), e.args),
                                              (RuntimeError, ('uh oh',)))])])
