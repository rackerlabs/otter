"""
:summary: Base Classes for Bobby Test Suites (Collections of Test Cases)
"""
from cafe.drivers.unittest.fixtures import BaseTestFixture
from cloudcafe.common.resources import ResourcePool
from bobby.client import BobbyAPIClient
from bobby.config import BobbyConfig
from bobby.behaviors import BobbyBehaviors
from cloudcafe.common.tools.datagen import rand_name


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
        cls.url = 'http://127.0.0.1:9876/849356'
        cls.bobby_client = BobbyAPIClient(cls.url, None, 'json', 'json')
        cls.bobby_config = BobbyConfig()
        cls.bobby_behaviors = BobbyBehaviors(cls.bobby_config,
                                             cls.bobby_client)
        # cls.autoscale_fixt = AutoscaleFixture()

        cls.tenant_id = cls.bobby_config.tenant_id
        cls.group_id = cls.bobby_config.group_id
        cls.notification = cls.bobby_config.notification
        cls.notification_plan = cls.bobby_config.notification_plan

    def validate_headers(self, headers):
        """
        Module to validate headers
        """
        self.assertTrue(headers is not None,
                        msg='No headers returned')
        if headers.get('transfer-encoding'):
            self.assertEqual(headers['transfer-encoding'], 'chunked',
                             msg='Response header transfer-encoding is not chunked')
        self.assertTrue(headers['server'] is not None,
                        msg='Response header server is not available')
        self.assertEquals(headers['content-type'], 'application/json',
                          msg='Response header content-type is None')
        self.assertTrue(headers['date'] is not None,
                        msg='Time not included')
        # self.assertTrue(headers['x-response-id'] is not None,
        #                 msg='No x-response-id')
        # the above is commented due to issue AUTO-596

    def assert_create_bobby_group_fields(self, group, group_id=None):
        """
        Assert the reponse of a bobby group
        """
        group_id = group_id or self.group_id
        self.assertEquals(group.tenantId, self.tenant_id,
                          msg='The tenant ID in the response did not match')
        self.assertEquals(group.groupId, group_id,
                          msg='The group ID in the response did not match')
        self.assertEquals(group.notification, self.notification,
                          msg='The notification in the response did not match')
        self.assertEquals(group.notificationPlan, self.notification_plan,
                          msg='The notification plan in the response did not match')

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

    @classmethod
    def setUpClass(cls, group_id=None, notification=None,
                   notification_plan=None):
        """
        Creates a group with default values
        """
        super(BobbyGroupFixture, cls).setUpClass()
        cls.group_id = rand_name('012345678-RAND-4543-85bc')
        notification = notification or cls.notification
        notification_plan = notification_plan or cls.notification_plan
        cls.create_group_response = cls.bobby_client.\
            create_group(group_id=cls.group_id, notification=notification,
                         notification_plan=notification_plan)
        cls.group = cls.create_group_response.entity
        cls.resources.add(group_id,
                          cls.bobby_client.delete_group)

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(BobbyGroupFixture, cls).tearDownClass()
