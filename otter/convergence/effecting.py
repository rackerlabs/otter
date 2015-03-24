"""Code related to effecting change based on a convergence plan."""

from effect import parallel

from otter.convergence.model import StepResult


def steps_to_effect(steps):
    """Turns a collection of :class:`IStep` providers into an effect."""
    # Treat unknown errors as RETRY.
    return parallel([
        s.as_effect().on(error=lambda e: (StepResult.RETRY, [e[1]]))
        for s in steps])
