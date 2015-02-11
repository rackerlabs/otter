"""
Tools for managing an undo stack and rewinding it to perform a series of
operations to clean up after an error.
"""

from zope.interface import Interface, implementer
from twisted.internet.defer import maybeDeferred


class IUndoStack(Interface):
    """
    A stack for which to record the information needed to undo some operations.
    """

    def push(f, *args, **kwargs):
        """
        Push a function ``f`` onto the undo stack.

        :param f: A function that will be called with the specified ``args`` and
            ``kwargs`` when the stack is rewound.
        """

    def rewind():
        """
        Rewind the undo stack. Rewinding will stop if an operation on the stack
        raises an exception or returns a Failure. The caller of
        :func:`IUndoStack.push` is expected to decide if an undo operation
        should raise an exception and stop rewinding.

        :rtype: ``Deferred``

        """


@implementer(IUndoStack)
class InMemoryUndoStack(object):
    """
    An Undo Stack that stores the operations in a local queue.
    """
    def __init__(self, coiterate):
        self._ops = []
        self._coiterate = coiterate

    def push(self, f, *args, **kwargs):
        """
        See :func:`IUndoStack.push`
        """
        self._ops.append((f, args, kwargs))

    def rewind(self):
        """
        See :func:`IUndoStack.rewind`
        """
        ops, self._ops = reversed(self._ops), []

        def run_ops():
            for (f, args, kwargs) in ops:
                yield maybeDeferred(f, *args, **kwargs)

        return self._coiterate(run_ops())
