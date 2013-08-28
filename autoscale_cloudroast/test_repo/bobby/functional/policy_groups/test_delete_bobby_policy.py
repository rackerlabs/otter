"""
Test delete bobby policy in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name


class DeleteBobbyPolicyTest(BobbyFixture):

    """
    Tests for delete group in bobby
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a bobby policy with the given policy id for given group id
        """
        super(DeleteBobbyPolicyTest, cls).setUpClass()
        cls.group_id = rand_name('TEST-GROUP-78f3-4543-85bc1')
        cls.policy_id = rand_name('TEST-POLICY-78f3-4543-85bc1')
        cls.bobby_policy = cls.bobby_behaviors.create_bobby_policy_given(
            group_id=cls.group_id,
            policy_id=cls.policy_id)

    def test_delete_bobby_policy_response(self):
        """
        Delete the bobby policy and verify the response code is 204.
        """
        delete_response = self.bobby_client.delete_bobby_policy(self.group_id,
                                                                self.policy_id)
        self.assertEquals(delete_response.status_code, 204,
                          msg='Deleting a bobby policy resulted in {0} as against '
                          ' 204'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)

    def test_delete_non_existant_group(self):
        """
        Delete a non existant group and verify the response code is 404.
        """
        delete_response = self.bobby_client.delete_bobby_policy(
            'I-DONT-EXIST', self.policy_id)
        self.assertEquals(delete_response.status_code, 404,
                          msg='Deleteing a bobby policy resulted in {0} as against '
                          ' 404 for an invalid groupId'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)

    def test_delete_non_existant_policy(self):
        """
        Delete a non existant policy and verify the response code is 404.
        """
        delete_response = self.bobby_client.delete_bobby_policy(
            self.group_id,
            'I-DONT-EXIST')
        self.assertEquals(delete_response.status_code, 404,
                          msg='Deleteing a bobby policy resulted in {0} as against '
                          ' 403 for an invalid serverId'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)
