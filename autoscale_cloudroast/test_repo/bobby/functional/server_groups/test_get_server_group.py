"""
Test get server groups in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name
import unittest


class GetServerGroupTest(BobbyFixture):

    """
    Get group tests
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a server group with the given server id for given group id
        """
        super(GetServerGroupTest, cls).setUpClass()
        cls.group_id = rand_name('TEST-GROUP-LINKS-78f3-4543-85bc1')
        cls.server_id = rand_name('TEST-SERVER-GROUP-LINKS-78f3-4543-85bc1')
        cls.server_group = cls.bobby_behaviors.create_bobby_server_group_given(
            group_id=cls.group_id,
            server_id=cls.server_id)
        cls.get_server_group_response = cls.bobby_client.get_server_group(
            cls.group_id,
            cls.server_id)
        cls.get_server_group = cls.get_server_group_response.entity

    def test_get_server_group_response(self):
        """
        Get a group, and verify the response code is 200 and validate
        the response object.
        """
        self.assertEquals(self.get_server_group_response.status_code, 200,
                          msg='Get group in bobby resulted in '
                          ' {0}'.format(self.get_server_group_response.status_code))
        self.validate_headers(self.get_server_group_response.headers)
        get_group = self.get_server_group_response.entity
        self.assertEquals(get_group.groupId, self.group_id,
                          msg='The groupId in the response does not match')
        self.assertEquals(get_group.serverId, self.server_id,
                          msg='The serverId in the response does not match')

    @unittest.skip('AUTO-570')
    def test_get_invalid_group(self):
        """
        Get a non existant group, and verify the response code is 404.
        """
        get_server_group_response = self.bobby_client.get_server_group(
            'BUT-I-DONT-EXIST', self.server_id)
        self.assertEquals(get_server_group_response.status_code, 404,
                          msg='Get for non existant group in bobby resulted in '
                          '{0}'.format(get_server_group_response.status_code))

    @unittest.skip('AUTO-570')
    def test_get_invalid_server_id(self):
        """
        Get a non existant server id, and verify the response code is 404.
        """
        get_server_group_response = self.bobby_client.get_server_group(
            self.group_id,
            'BUT-I-DONT-EXIST')
        self.assertEquals(get_server_group_response.status_code, 404,
                          msg='Get for non existant group in bobby resulted in '
                          '{0}'.format(get_server_group_response.status_code))
