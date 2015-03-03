"""This module contains entities useful for representing shared state in
integration tests.
"""

from characteristic import Attribute, attributes


@attributes([
    Attribute('access', default_value=None),
    Attribute('endpoints', default_value={}),
    Attribute('groups', default_value=[]),
    Attribute('clbs', default_value=[]),
])
class TestResources(object):
    """This class records the various resources used by a test.
    It is NOT intended to be used for clean-up purposes (use
    :func:`unittest.addCleanup` for this purpose).  Instead, it's just a
    useful scratchpad for passing test resource availability amongst Twisted
    callbacks.

    If you have custom state you'd like to pass around, use the :attr:`other`
    attribute for this purpose.  The library will not interpret this attribute,
    nor will it change it (bugs notwithstanding).
    """
