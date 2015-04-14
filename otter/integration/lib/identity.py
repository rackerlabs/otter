"""This module contains reusable Identity components."""

from characteristic import Attribute, attributes

from pyrsistent import freeze


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

        return self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool
        ).addCallback(rcs.init_from_access)


def find_endpoint(catalog, service_type, region):
    """Locate an endpoint in a service catalog, as returned by IdentityV2.
    Please note that both :param:`service_type` and :param:`region` are
    case sensitive.

    :param dict catalog: The Identity service catalog.
    :param str service_type: The type of service to look for.
    :param str region: The service region the desired endpoint must service.
    :return: The endpoint offering the desired type of service for the
        desired region, if available.  None otherwise.
    """
    for entry in catalog["access"]["serviceCatalog"]:
        if entry["type"] != service_type:
            continue
        for endpoint in entry["endpoints"]:
            if endpoint["region"] == region:
                return endpoint["publicURL"]
    return None
