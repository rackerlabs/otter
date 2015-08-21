"""This module contains reusable Identity components."""

from characteristic import Attribute, attributes

from otter.integration.lib.utils import diagnose


@attributes([
    Attribute('auth'),
    Attribute('username', instance_of=str),
    Attribute('password', instance_of=str),
    Attribute('endpoint', instance_of=str),
    Attribute('pool', default_value=None),
    Attribute('convergence_tenant_override', default_value=None),
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

    @diagnose("Identity", "Authing test user")
    def authenticate_user(self, rcs, resources=None, region=None):
        """Authenticates against the Identity API.  Prior to success, the
        :attr:`access` member will be set to `None`.  After authentication
        completes, :attr:`access` will hold the raw Identity V2 API results as
        a Python dictionary, including service catalog and API authentication
        token.

        :param TestResources rcs: A :class:`TestResources` instance used to
            record the identity results.
        :param dict resources: A dictionary that maps a `TestResources` service
            catalog key to a tuple.  The tuple, then, contains the actual
            service catalog key, and default URL (or None if not).  For
            example, {"nova": ("cloudComputeOpenStack",), "autoscale":
            ("rax:autoscale", "http://localhost:9000/v1.0")}.
        :param string region: Required if `resources` provided; ignored
            otherwise.  This provides the OpenStack region to use for all
            service catalog queries.
        :return: A Deferred which, when fired, returns a copy of the resources
            given.  The :attr:`access` field will be set to the Python
            dictionary representation of the Identity authentication results.
        """
        resources = resources or {}

        d = self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool,
            tenant_id=self.convergence_tenant_override,
        ).addCallback(rcs.init_from_access)

        for r in resources:
            # This pads the provided tuple or list out to the minimum length
            # needed to perform the multi-assignment.  Saves on special-cases.
            service_catalog_key, default_url = (resources[r]+(None,))[:2]

            kwArgs = {}
            if default_url:
                kwArgs = {"default_url": default_url}

            d.addCallback(
                rcs.find_end_point,
                r, service_catalog_key, region,
                **kwArgs
            )
        return d


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
