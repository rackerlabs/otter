"""
Mixins and utilities to be used for testing.
"""
import mock
import os

from zope.interface import directlyProvides

from twisted.python.failure import Failure
from twisted.internet.defer import Deferred


class DeferredTestMixin(object):
    """
    Class that can be used for asserting whether a ``Deferred`` has fired or
    failed
    """

    def assert_deferred_fired(self, deferred):
        """
        Asserts that the deferred has fired (either an errback or a callback),
        and returns the result (either the return value or the failure)

        :param deferred: the ``Deferred`` to check
        :type deferred: :class:`twisted.internet.defer.Deferred`

        :return: whatever the ``Deferred`` fires with, or a
            :class:`twisted.python.failure.Failure`
        """
        if not isinstance(deferred, Deferred):
            self.fail("Not a deferred")

        output = []
        deferred.addBoth(lambda result: output.append(result))
        self.assertTrue(len(output) == 1, "Deferred should have fired")
        return output[0]

    def assert_deferred_succeeded(self, deferred):
        """
        Asserts that the deferred has callbacked, and not errbacked, and
        returns the result.

        :param deferred: the ``Deferred`` to check
        :type deferred: :class:`twisted.internet.defer.Deferred`

        :return: whatever the ``Deferred`` fires with
        """
        result = self.assert_deferred_fired(deferred)
        if isinstance(result, Failure):
            self.fail("Deferred errbacked with {0!r}".format(result))
        return result

    def assert_deferred_failed(self, deferred, *expected_failures):
        """
        Asserts that the deferred should have errbacked with the given
        expected failures.  This is like
        :func:`twisted.trial.unittest.TestCase.assertFailure` except that it
        asserts that it has _already_ failed.

        :param deferred: the ``Deferred`` to check
        :type deferred: :class:`twisted.internet.defer.Deferred`

        :param expected_failures: all the failures that are expected.  If None,
            will return true so long as the deferred errbacks, with whatever
            error.  If provided, ensures that the failure matches
            one of the expected failures.
        :type expected_failures: Exceptions

        :return: whatever the Exception was that was expected, or None if the
            test failed
        """
        result = self.assert_deferred_fired(deferred)
        if not isinstance(result, Failure):
            self.fail("Did not errback - instead callbacked with {0!r}".format(
                result))
        else:
            if (len(expected_failures) > 0 and
                    not result.check(*expected_failures)):
                self.fail('\nExpected: {0!r}\nGot:\n{1!s}'.format(
                    expected_failures, result))
        return result


def fixture(fixture_name):
    """
    :param fixture_name: The base filename of the fixture, ex: simple.atom.
    :type: ``bytes``

    :returns: ``bytes``
    """
    return open(os.path.join(
        os.path.dirname(__file__),
        'fixtures',
        fixture_name
    )).read()


def iMock(iface, **kwargs):
    """
    Creates a mock object that provides a particular interface.

    :param iface: the interface to provide
    :type iface: :class:``zope.interface.Interface``

    :returns: a mock object that is specced to have the attributes and methods
        as a provider of the interface
    :rtype: :class:``mock.MagicMock``
    """
    if 'spec' in kwargs:
        del kwargs['spec']

    imock = mock.MagicMock(spec=iface.names(), **kwargs)
    directlyProvides(imock, iface)
    return imock
