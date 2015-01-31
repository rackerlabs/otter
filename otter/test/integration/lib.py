"""The lib module provides a library of classes and functions useful for
writing integration tests in the context of the Otter project.
"""

from twisted.web.client import HTTPConnectionPool

from characteristic import Attribute, attributes


@attributes([
    Attribute('auth'),
    Attribute('username', instance_of=str),
    Attribute('password', instance_of=str),
    Attribute('endpoint', instance_of=str),
    Attribute('pool', instance_of=HTTPConnectionPool, default_value=None),
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

    def authenticate_user(self):
        return self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool
        )


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
