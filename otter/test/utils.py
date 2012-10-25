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

        results = []
        deferred.addBoth(lambda result: results.append(result))
        self.assertTrue(len(results) == 1, "Deferred should have fired")
        return results[0]

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

        results = []

        def _cb(results):
            results.append(None)
            self.fail("Did not errback - instead callbacked with {0!r}".format(
                results))

        def _eb(failure):
            if (len(expected_failures) == 0 or
                    failure.check(*expected_failures)):
                results.append(failure.value)
            else:
                results.append(None)
                self.fail('\nExpected: {0!r}\nGot:\n{1!s}'.format(
                    expected_failures, failure))

        deferred.addCallbacks(_cb, _eb)
        self.assertTrue(len(results) == 1, "Deferred should have fired")
        return results[0]
