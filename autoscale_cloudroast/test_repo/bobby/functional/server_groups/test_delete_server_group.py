"""
Test delete server group in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name


class DeleteServerGroupTest(BobbyFixture):

    """
    Tests for delete group in bobby
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a server group with the given server id for given group id
        """
        super(DeleteServerGroupTest, cls).setUpClass()
        cls.group_id = rand_name('TEST-GROUP-78f3-4543-85bc1')
        cls.server_id = rand_name('TEST-SERVER-GROUP-78f3-4543-85bc1')
        cls.server_group = cls.bobby_behaviors.create_bobby_server_group_given(
            group_id=cls.group_id,
            server_id=cls.server_id)

    def test_delete_group_response(self):
        """
        Delete the group and verify the response code is 204.
        """
        delete_response = self.bobby_client.delete_server_group(self.group_id,
                                                                self.server_id)
        self.assertEquals(delete_response.status_code, 204,
                          msg='Deleting a server group resulted in {0} as against '
                          ' 204'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)

    def test_delete_non_existant_group(self):
        """
        Delete a non existant group and verify the response code is 404.
        """
        delete_response = self.bobby_client.delete_server_group(
            'I-DONT-EXIST', self.server_id)
        self.assertEquals(delete_response.status_code, 404,
                          msg='Deleteing a server group resulted in {0} as against '
                          ' 404 for an invalid groupId'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)

    def test_delete_non_existant_server(self):
        """
        Delete a non existant server and verify the response code is 404.
        """
        delete_response = self.bobby_client.delete_server_group(
            self.group_id,
            'I-DONT-EXIST')
        self.assertEquals(delete_response.status_code, 404,
                          msg='Deleteing a server group resulted in {0} as against '
                          ' 404 for an invalid serverId'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)
