"""
Contains the base Klein app for Otter.
"""

from klein import Klein


class OtterApp(Klein):
    """
    Base app that extends Klein to override route.
    """
    def route(self, *args, **kwargs):
        """
        Default strict_slashes to False
        """
        kwargs['strict_slashes'] = False
        return super(OtterApp, self).route(*args, **kwargs)
