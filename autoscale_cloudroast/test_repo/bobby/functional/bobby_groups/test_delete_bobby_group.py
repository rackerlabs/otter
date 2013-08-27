"""
Test delete group in bobby
"""
from test_repo.bobby.fixtures import BobbyGroupFixture
from cloudcafe.common.tools.datagen import rand_name


class DeleteGroupTest(BobbyGroupFixture):

    """
    Tests for delete group in bobby
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a group with the given group id
        """
        cls.group_id_temp = rand_name('012345678-2222-4543-85bc-')
        super(DeleteGroupTest, cls).setUpClass(group_id=cls.group_id_temp)

    def test_delete_group_response(self):
        """
        Delete the group and verify the response code is 204.
        """
        delete_response = self.bobby_client.delete_group(self.group_id_temp)
        self.assertEquals(delete_response.status_code, 204,
                          msg='Deleting a group resulted in {0} as against '
                          ' 204'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)

    def test_delete_non_existant_group(self):
        """
        Delete a non existant group and verify the response code is 403.
        """
        delete_response = self.bobby_client.delete_group('I-DONT-EXIST')
        self.assertEquals(delete_response.status_code, 403,
                          msg='Deleteing a group resulted in {0} as against '
                          ' 403'.format(delete_response.status_code))
        self.validate_headers(delete_response.headers)
