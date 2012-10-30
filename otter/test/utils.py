"""
Mixins and utilities to be used for testing.
"""

from twisted.internet import defer


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
        if not isinstance(deferred, defer.Deferred):
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
        if not isinstance(deferred, defer.Deferred):
            self.fail("Not a deferred")

        output = []
        deferred.addCallback(lambda result: output.append(result))
        self.assertTrue(len(output) == 1, "Deferred did not succeed")
        return output[0]

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
        if not isinstance(deferred, defer.Deferred):
            self.fail("Not a deferred")

        output = []

        def _cb(result):
            output.append(None)
            self.fail("Did not errback - instead callbacked with {0!r}".format(
                result))

        def _eb(failure):
            if (len(expected_failures) == 0 or
                    failure.check(*expected_failures)):
                output.append(failure.value)
            else:
                output.append(None)
                self.fail('\nExpected: {0!r}\nGot:\n{1!s}'.format(
                    expected_failures, failure))

        deferred.addCallbacks(_cb, _eb)
        self.assertTrue(len(output) == 1, "Deferred should have fired")
        return output[0]
