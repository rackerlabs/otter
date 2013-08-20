"""
Contains the BaseApp all Otter klein apps inherit from.
"""

from functools import partial

from klein import Klein


class BaseApp(object):
    """
    BaseApp sets up a new Klein app with non-strict slashes, and all
    contenttypes set to JSON.
    """
    def __init__(self, store, *args, **kwargs):
        """
        :param store: The application data store.
        """
        self.app = Klein()
        self.store = store
        self.app.route = partial(self.app.route, strict_slashes=False)

        # everything should be json
        resource = self.app.resource()
        resource.defaultContentType = 'application/json'
