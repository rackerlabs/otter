"""Effect dispatchers for Otter."""

from effect import base_dispatcher, ComposedDispatcher
from effect.twisted import legacy_dispatcher, make_twisted_dispatcher


def get_dispatcher(reactor):
    """
    Get an Effect dispatcher that can handle all the effects in Otter,
    suitable for passing to :func:`effect.perform`.
    """
    # TODO: Get rid of the "legacy_dispatcher" here, after we get rid of all use
    # of "perform_effect" methods on intents.
    return ComposedDispatcher([
        base_dispatcher,
        legacy_dispatcher,
        make_twisted_dispatcher(reactor),
    ])
