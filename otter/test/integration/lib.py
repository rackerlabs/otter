"""The lib module provides a library of classes and functions useful for
writing integration tests in the context of the Otter project.
"""


class IdentityV2(object):
    """This class provides a way to configure commonly used parameters
    exactly once for any number of Identity-related API calls.
    """

    def __init__(self, auth, username, password, endpoint, pool=None):
        """Creates and configures the IdentityV2 instance with the
        parameters provided.

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
        :raises ValueError: Username, password, and endpoint all must be
            provided.  If any one are not present, this exception will be
            raised.
        """
        def validate(param, name):
            if not param:
                raise ValueError("{} required".format(name))
            if not isinstance(param, str):
                raise ValueError("{} must be string".format(name))

        validate(username, "username")
        validate(password, "password")
        validate(endpoint, "endpoint")

        self.auth = auth
        self.username = username
        self.password = password
        self.endpoint = endpoint
        self.pool = pool

    def authenticate_user(self):
        return self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool
        )
