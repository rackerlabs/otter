"""
State storage for AtomHopper poller
"""

from zope.interface import Interface, implements

import os

from twisted.internet import defer


class IStateStore(Interface):
    """
    Interface the :mod:`otter.indexer.poller` expects for storing state
    """
    def get_state():
        """
        :returns: `Deferred` that fires with the current state.
        """

    def save_state(state):
        """
        :param state: object representing the current state.

        :returns: `Deferred` that fires when the state has been saved.
        """


class DummyStateStore(object):
    """
    Fake state store that doesn't actually store the state.
    """
    def get_state(self):
        """Always returns no state.

        :return: ``Deferred`` that callbacks immediately with None
        """
        return defer.succeed(None)

    def save_state(self, state):
        """Does not actually save state.

        :return: ``Deferred`` that callbacks immediately with None
        """
        return defer.succeed(None)


class FileStateStore(object):
    """
    State storage that saves state to and loads state from a file.

    :ivar filename: the name of the file to which state is saved and from
        which state is loaded
    :type filename: ``str``
    """
    implements(IStateStore)

    def __init__(self, filename):
        self.filename = filename

    def get_state(self):
        """Reads state from the file.

        :returns: `Deferred` that fires with the current state.
        """
        def _read():
            if os.path.exists(self.filename):
                return open(self.filename).read()

        return defer.execute(_read)

    def save_state(self, state):
        """Saves state to the file.

        :type state: ``base_string``

        :returns: `Deferred` that fires when the state has been saved.
        """
        if state:
            open(self.filename, 'w').write(state)

        return defer.succeed(None)
