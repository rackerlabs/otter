"""
Test get and list groups in bobby
"""
from test_repo.bobby.fixtures import BobbyGroupFixture
from cloudcafe.common.tools.datagen import rand_name


class GetGroupTest(BobbyGroupFixture):

    """
    Verify get a newly created group in bobby. Delete the group.
    Verify the delete was successful by doing a GET on the group
    that results in 404.
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a group with the given group id
        """
        cls.group_id_temp = rand_name('012345678-78f3-4543-85bc-')
        super(GetGroupTest, cls).setUpClass(group_id=cls.group_id_temp)
        cls.get_group_response = cls.bobby_client.get_group(cls.group_id_temp)
        cls.group = cls.get_group_response.entity

    def test_get_group_response(self):
        """
        Get a group, and verify the response code is 200.
        """
        self.assertEquals(self.get_group_response.status_code, 200,
                          msg='Get group in bobby resulted in {0}'.format(
                          self.get_group_response.status_code))
        self.validate_headers(self.get_group_response.headers)
        get_group = self.get_group_response.entity
        self.assert_create_bobby_group_feilds(get_group, self.group_id_temp)

    def test_list_group_response(self):
        """
        Create multiple groups. List group, and verify the response code is 200.
        """
        group1 = self.bobby_behaviors.create_bobby_group_min()
        group2 = self.bobby_behaviors.create_bobby_group_min()
        list_group_response = self.bobby_client.list_groups(self.group_id)
        self.assertEquals(list_group_response.status_code, 200,
                          msg='List group in bobby resulted in {0}'.format(
                          list_group_response.status_code))
        self.validate_headers(list_group_response.headers)
        self.assertTrue(group1.groupId in list_group_response.entity)
        self.assertTrue(group2.groupId in list_group_response.entity)

