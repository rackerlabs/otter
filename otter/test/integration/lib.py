"""The lib module provides a library of classes and functions useful for
writing integration tests in the context of the Otter project.
"""

from characteristic import Attribute, attributes


@attributes([
    Attribute('access', default_value=None),
    Attribute('other', default_value=None),
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


@attributes([
    Attribute('auth'),
    Attribute('username', instance_of=str),
    Attribute('password', instance_of=str),
    Attribute('endpoint', instance_of=str),
    Attribute('pool', default_value=None),
])
class IdentityV2(object):
    """This class provides a way to configure commonly used parameters
    exactly once for any number of Identity-related API calls.

    :param module auth: Either the ``otter.auth`` module, or a compatible
        interface for testing purposes.
    :param str username: The username you wish to authenticate against
        Identity with.
    :param str password: The password you wish to authenticate against
        Identity with.
    :param str endpoint: The Identity V2 API base endpoint address.
    :param twisted.web.client.HTTPConnectionPool pool: If left
        unspecified, Twisted will use its own connection pool for making
        HTTP requests.  When running tests via Trial, this may cause
        some race conditions inside the treq module.  Providing your
        own connection pool for manual management inside of a test class'
        setUp and tearDown methods will work around this problem.
        See https://github.com/dreid/treq/blob/master/treq/
        test/test_treq_integration.py#L60-L74 for more information.
    """

    def __init__(self):
        self.access = None

    def authenticate_user(self, rcs):
        """Authenticates against the Identity API.  Prior to success, the
        :attr:`access` member will be set to `None`.  After authentication
        completes, :attr:`access` will hold the raw Identity V2 API results as
        a Python dictionary, including service catalog and API authentication
        token.

        :param TestResources rcs: A :class:`TestResources` instance used to
            record the identity results.

        :return: A Deferred which, when fired, returns a copy of the resources
            given.  The :attr:`access` field will be set to the Python
            dictionary representation of the Identity authentication results.
        """

        def record_result(r):
            rcs.access = r
            return rcs

        return self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool
        ).addCallback(record_result)


def find_endpoint(catalog, kind, region):
    """Locate an endpoint in a service catalog, as returned by IdentityV2.

    :param dict catalog: The Identity service catalog.
    :param str kind: The "type" of service to look for.
        We name the parameter ``kind`` only because ``type`` is a reserved
        word in Python.
    :param str region: The service region the desired endpoint must service.
    :return: The endpoint offering the desired kind of service for the
        desired region, if available.  None otherwise.
    """
    for entry in catalog["access"]["serviceCatalog"]:
        if entry["type"] != kind:
            continue
        for endpoint in entry["endpoints"]:
            if endpoint["region"] == region:
                return endpoint["publicURL"]
    return None
