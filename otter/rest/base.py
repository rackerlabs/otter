"""
Contains the BaseApp all Otter klein apps inherit from.
"""

from functools import partial


class BaseApp(object):
    """
    BaseApp sets up a new Klein app with non-strict slashes, and all
    contenttypes set to JSON.
    """
    def __init__(self, store, *args, **kwargs):
        """
        :param store: The application data store.
        """
        self.store = store

        # BaseApp inheriters will be required to have a class variable app.
        self.app.route = partial(self.app.route, strict_slashes=False)
