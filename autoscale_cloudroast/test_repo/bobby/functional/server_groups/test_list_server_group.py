"""
Test list server groups in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name


class ListServerGroupTest(BobbyFixture):
    """
    Tests for list server group
    """

    def test_list_server_group_response(self):
        """
        Create multiple server groups. List server group, and verify the response code is 200.
        """
        group_id = rand_name('0123GROUP-78f3-4543-85bc1-')
        server_id_1 = rand_name('0123SERVERGROUP-78f3-4543-85bc1-')
        server_id_2 = rand_name('0123SERVERGROUP-78f3-4543-85bc2-')
        self.bobby_behaviors.create_bobby_server_group_given(group_id=group_id,
                                                             server_id=server_id_1)
        self.bobby_behaviors.create_bobby_server_group_given(group_id=group_id,
                                                             server_id=server_id_2)
        list_group_response = self.bobby_client.list_server_groups(group_id)
        self.assertEquals(list_group_response.status_code, 200,
                          msg='List server group in bobby resulted in '
                          ' {0}'.format(list_group_response.status_code))
        self.validate_headers(list_group_response.headers)
        server_group_id_list = [
            each_group.serverId for each_group in list_group_response.entity]
        self.assertTrue(server_id_1 in server_group_id_list, msg='Server Group with id'
                        '{0} does not exist when listing server groups: '
                        ' {1}'.format(server_id_1, server_group_id_list))
        self.assertTrue(server_id_2 in server_group_id_list, msg='Server Group with id'
                        '{0} does not exist when listing server groups: '
                        ' {1}'.format(server_id_2, server_group_id_list))
