"""
:summary: Base Classes for Bobby Test Suites (Collections of Test Cases)
"""
from cafe.drivers.unittest.fixtures import BaseTestFixture
from cloudcafe.common.resources import ResourcePool
#from autoscale.config import AutoscaleConfig
from bobby.client import BobbyAPIClient


class BobbyFixture(BaseTestFixture):

    """
    :summary: Fixture for an Bobby tests.
    """

    @classmethod
    def setUpClass(cls):
        """
        Initialize bobby client and set up authentication
        """
        super(BobbyFixture, cls).setUpClass()
        cls.resources = ResourcePool()
        cls.url = 'http://127.0.0.1:9876/829409'
        cls.bobby_client = BobbyAPIClient(cls.url, None, 'json', 'json')

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the added bobby resources
        """
        super(BobbyFixture, cls).tearDownClass()
        cls.resources.release()


class BobbyGroupFixture(BobbyFixture):

    """
    :summary: Creates a group using the default from
              the test data
    """
    pass

    @classmethod
    def setUpClass(cls, group_id=None, notification=None,
                   notification_plan=None):
        """
        Creates a group with default values
        """
        super(BobbyGroupFixture, cls).setUpClass()
        group_id = group_id or '90364858-78f3-4543-85bc-e75a407c08d4'

        cls.create_group_response = cls.bobby_client.\
            create_group(group_id=group_id)
        cls.group = cls.create_group_response.entity
        cls.resources.add(cls.group.id,
                          cls.bobby_client.delete_group)

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(BobbyGroupFixture, cls).tearDownClass()
