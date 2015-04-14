"""This module contains entities useful for representing shared state in
integration tests.
"""

from characteristic import Attribute, attributes

from pyrsistent import freeze

from twisted.internet.defer import Deferred

from otter import auth


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
    """

    def init_from_access(self, acc):
        """After authenticating from Identity API, this function takes the
        resulting JSON "access" structure, and extracts from it important
        information to enable invoking API calls later.

        :param dict acc: The parsed JSON "access" response from authenticating
            with Identity API.

        :return: Self, as it's intended to be used as a Deferred callback.
        """

        self.access = freeze(acc)
        self.tenant = self.access["access"]["token"]["tenant"]["id"]
        self.token = self.access["access"]["token"]["id"]
        self.sc = self.access["access"]["serviceCatalog"]
        return self

    def find_end_point(self, _, key, service_type, region, default_url=None):
        """Initialize the instance with the endpoint required for later test
        execution.

        :param str key: The dictionary key to store the resulting endpoint URL
            under.  Supported keys are listed above.
        :param str service_type: The kind of service to look for in the service
            catalog.  For example, "cloudServersOpenStack" or "autoscale".
        :param str region: The region under which to look for the endpoint.
        :param str default_url: If provided, a template that can be used to
            compute a well-known endpoint.  For example, if you're developing
            an implementation of a new service and using a set of mocks,
            you'll want to hide any mock version of your service, and use the
            endpoint your daemon provides in lieu of any mock.  For example,
            "http://localhost:9000/v1.0/{0}.  Note that {0} expands to the
            OpenStack tenant ID.

        :return: self.
        """

        try:
            self.endpoints[key] = auth.public_endpoint_url(
                self.sc, service_type, region
            )
        except auth.NoSuchEndpoint:
            if not default_url:
                raise
            self.endpoints[key] = default_url.format(self.tenant)

        d = Deferred()
        d.callback(self)  # really wish this didn't return None.
        return d
