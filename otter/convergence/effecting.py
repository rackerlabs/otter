"""Code related to effecting change based on a convergence plan."""

from effect import parallel


def steps_to_effect(steps):
    """Turns a collection of :class:`IStep` providers into an effect."""
    return parallel([s.as_effect() for s in steps])
