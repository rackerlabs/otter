"""Tests for convergence effecting."""

from effect import Constant, Effect, Error, ParallelEffects, sync_perform

from testtools.matchers import MatchesException

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.effecting import steps_to_effect
from otter.convergence.model import ErrorReason, StepResult
from otter.test.utils import TestStep, matches, test_dispatcher


class StepsToEffectTests(SynchronousTestCase):
    """Tests for :func:`steps_to_effect`"""
    def test_uses_step_request(self):
        """Steps are converted to requests."""
        steps = [TestStep(Effect(Constant((StepResult.SUCCESS, 'foo')))),
                 TestStep(Effect(Error(RuntimeError('uh oh'))))]
        effect = steps_to_effect(steps)
        self.assertIs(type(effect.intent), ParallelEffects)
        expected_exc_info = matches(MatchesException(RuntimeError('uh oh')))
        self.assertEqual(
            sync_perform(test_dispatcher(), effect),
            [(StepResult.SUCCESS, 'foo'),
             (StepResult.RETRY,
              [ErrorReason.Exception(expected_exc_info)])])
