"""
Test to create and verify the created group in bobby.
"""
from test_repo.bobby.fixtures import BobbyFixture


class CreateGroupTest(BobbyFixture):

    """
    Verify create group in bobby.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a group in bobby.
        """
        super(CreateGroupTest, cls).setUpClass()
        cls.scaling_group_id = '90364858-78f3-4543-85bc-e75a407c08d4'
        cls.notification = 'test@test.com'
        cls.notification_plan = {'label': 'TestNP', 'critical_state': ['test']}

    @classmethod
    def tearDownClass(cls):
        """
        Delete group in bobby
        """

    def test_create_group_response(self):
        """
        Create a group in bobby with a given group_id, notification
        and notification pals, and verify the response code is 201.
        """
        create_group_response = self.bobby_client.create_group(
            group_id=self.scaling_group_id,
            notification=self.notification,
            notification_plan=self.notification_plan)
        self.assertEquals(create_group_response.status_code, 201,
                          msg='The response code for create  group in bobby '
                          'resulted in {0}'.format(create_group_response.status_code))
        self.resources.add(self.scaling_group_id,
                           self.autoscale_client.delete_group)

    def test_create_group_with_bad_request(self):
        """
        Create a group in bobby with a given group_id, notification
        and notification pals, and verify the response code is 201.
        """
        scaling_group_id = '90364858-78f3-4543-85bc-e75a407c08d4'
        create_group_response = self.bobby_client.create_group(
            group_id=scaling_group_id,
            notification='lekha.jeevan@rackspace.com',
            notification_plan=None)
        self.assertEquals(create_group_response.status_code, 201,
                          msg='The response code for create  group in bobby '
                          'resulted in {0}'.format(create_group_response.status_code))
        self.resources.add(scaling_group_id,
                           self.autoscale_client.delete_group)
