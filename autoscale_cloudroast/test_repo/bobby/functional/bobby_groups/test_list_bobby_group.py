"""
Test list groups in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name


class ListGroupTest(BobbyFixture):
    """
    Test for list groups
    """

    def test_list_group_response(self):
        """
        Create multiple groups. List group, and verify the response code is 200.
        """
        group_id_1 = rand_name('012345678-78f3-4543-85bc1-')
        group_id_2 = rand_name('012345678-78f3-4543-85bc2-')
        self.bobby_behaviors.create_bobby_group_given(group_id_1)
        self.bobby_behaviors.create_bobby_group_given(group_id_2)
        list_group_response = self.bobby_client.list_groups()
        self.assertEquals(list_group_response.status_code, 200,
                          msg='List group in bobby resulted in '
                          ' {0}'.format(list_group_response.status_code))
        self.validate_headers(list_group_response.headers)
        group_id_list = [each_group.groupId for each_group in list_group_response.entity]
        self.assertTrue(group_id_1 in group_id_list, msg='Group with id'
                        '{0} does not exist when listing groups: {1}'.format(group_id_1,
                                                                             group_id_list))
        self.assertTrue(group_id_2 in group_id_list, msg='Group with id'
                        '{0} does not exist when listing groups: {1}'.format(group_id_2,
                                                                             group_id_list))
