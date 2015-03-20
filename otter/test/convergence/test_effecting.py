"""Tests for convergence effecting."""

from effect import Constant, Effect, ParallelEffects, ComposedDispatcher, TypeDispatcher, base_dispatcher, sync_perform, Error
from effect.async import perform_parallel_async

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import implementer

from otter.convergence.effecting import steps_to_effect
from otter.convergence.model import StepResult
from otter.convergence.steps import IStep
from otter.test.utils import transform_eq


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
        dispatcher = ComposedDispatcher([
            base_dispatcher,
            TypeDispatcher({ParallelEffects: perform_parallel_async}),
        ])
        self.assertEqual(
            sync_perform(dispatcher, effect),
            [(StepResult.SUCCESS, 'foo'),
             (StepResult.RETRY, [transform_eq(lambda e: (type(e), e.args),
                                              (RuntimeError, ('uh oh',)))])])
