"""
Mixins and utilities to be used for testing.
"""
import mock
from cStringIO import StringIO

from twisted.python.failure import Failure
from twisted.internet.defer import Deferred, succeed


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


def mock_agent_request(request_deferred, return_value=None):
    """
    A function to get a fake :func:`twisted.web.client.Agent.request` method -
    this method records the http method, uri, headers, and the content of a
    bodyProducer.

    This method is used because the reactor needs to actually spin to get
    certain implementations of :class:`IBodyProducer` to finish writing all
    bytes to its consumer.  Therefore, the ``request_deferred`` that is
    provided to this function should be returned at the end of a test method.

    :param return_value: What the deferred returned by the mock method should
        fire with. Defaults to a mock request with a 204 status code and no
        body.
    :type return_value: Some kind of mock request object that provides some of
        :class:`twisted.web.iweb.IResponse`

    :return: A fake request method, that when called, will return a deferred
        that will fire with whatever the return value provided was.  Also,
        a ``dict`` of the method, uri, headers, and body the fake method was
        called with will be fired from the deferred provided to this function
        when the body of the request has finished writing all bytes.
    :rtype: ``func``
    """
    def request(method, uri, headers=None, bodyProducer=None):
        """
        The fake Agent.request method that records all the information
        """
        def _cb(_, body_strio=None):
            body = ''
            if body_strio is not None:
                body = body_strio.getvalue()

            request_deferred.callback({
                'method': method,
                'uri': uri,
                'headers': headers,
                'body': body
            })

        if bodyProducer is None:
            _cb(None)
        else:
            body = StringIO()  # not an IConsumer, but only write is called
            # IBodyProducer's startProducing returns a Deferred that fires
            # with a None when all bytes have finished writing
            bodyProducer.startProducing(body).addCallback(_cb, body)

        if return_value is None:
            return succeed(mock.MagicMock(code=204, content=StringIO()))
        else:
            return succeed(return_value)

    return request

