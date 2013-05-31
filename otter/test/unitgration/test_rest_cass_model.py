"""
Integration-y tests for the REST interface interacting with the Cassandra model.

This is perhaps not the place for these tests to go.  Also, perhaps this should
instead be tested by spinning up an actually HTTP server (thus this test can
happen using the mock tap file).

But until a decision has been made for integration test infrastructure and
frameworks, this will do for now, as it is needed to verify that the rest unit
tests and Cassandra model unit tests do not lie.
"""
from otter.models.cass import CassScalingGroupCollection
from otter.test.resources import OtterKeymaster

from otter.test.unitgration.test_rest_mock_model import (
    MockStoreRestScalingGroupTestCase,
    MockStoreRestScalingPolicyTestCase
)

try:
    keymaster = OtterKeymaster()
except Exception as e:
    skip = "Cassandra unavailable: {0}".format(e)
else:
    keyspace = keymaster.get_keyspace()
    store = CassScalingGroupCollection(keyspace.client)


class BaseCassandraStoreMixin(object):
    def create_store(self):
        keyspace.resume()
        return store

    def tearDown(self):
        keyspace.dirtied()
        keyspace.pause()
        keyspace.reset(self.mktemp())


class CassStoreRestScalingGroupTestCase(BaseCassandraStoreMixin, MockStoreRestScalingGroupTestCase):
    """
    Test case for testing the REST API for the scaling group specific endpoints
    (not policies or webhooks) against the Cassandra model.
    """


class CassStoreRestScalingPolicyTestCase(BaseCassandraStoreMixin, MockStoreRestScalingPolicyTestCase):
    """
    Test case for testing the REST API for the scaling policy specific endpoints
    (but not webhooks) against the mock model.

    As above, this could be made a base case instead... yadda yadda.
    """
