"""
Test to create and verify server group in bobby.
"""
from test_repo.bobby.fixtures import BobbyFixture
import unittest


class CreateServerGroupTest(BobbyFixture):

    """
    Verify create server group in bobby.
    """

    def test_create_server_group_response(self):
        """
        Create a server group in bobby, and verify the response code is 201,
        the headers and the response object.
        """
        server_id = '012345678-SERVERGROUP-4543-85bc'
        entity_id = '87678687687'
        create_server_group_response = self.bobby_behaviors.create_bobby_server_group_given(
            server_id=server_id,
            entity_id=entity_id)
        self.assertEquals(create_server_group_response.status_code, 201,
                          msg='The response code for create  group in bobby '
                          'resulted in {0}'.format(create_server_group_response.status_code))
        self.validate_headers(create_server_group_response.headers)
        server_group = create_server_group_response.entity
        self.assertEquals(server_group.groupId, self.group_id,
                          msg='The groupId in the response does not match')
        self.assertEquals(server_group.serverId, server_id,
                          msg='The serverId in the response does not match')
        self.assertEquals(server_group.entityId, entity_id,
                          msg='The entityId in the response does not match')

    @unittest.skip('AUTO-571')
    def test_create_groups_with_same_server_entity_ids(self):
        """
        Create a server group in bobby with the same server and entity IDs and verify server
        and entity ids has to be unique. If not 403 is returned.
        """
        server_id = 'SERVER-78f3-4543-85bc-e75a407c08d4'
        entity_id = 'ENTITY-78f3-4543-85bc-e75a407c08d4'
        group1_response = self.bobby_behaviors.create_bobby_server_group_given(
            server_id=server_id,
            entity_id=entity_id)
        self.assertEquals(group1_response.status_code, 201, msg='Create server'
                          ' group in bobby failed with {0}'.format(group1_response.status_code))
        group2_response = self.bobby_behaviors.create_bobby_server_group_given(
            server_id=server_id,
            entity_id=entity_id)
        self.assertEquals(group2_response.status_code, 403, msg='Create server'
                          ' group, with already existing server and entity ID in bobby, failed'
                          ' with {0}'.format(group2_response.status_code))

    def test_create_group_without_server_id(self):
        """
        Create a server group in bobby without a server_id, and verify the
        response code is 400.
        """
        create_group_response = self.bobby_client.create_server_group(
            group_id=self.group_id,
            server_id=None,
            entity_id='TESTS')
        self.assertEquals(create_group_response.status_code, 400,
                          msg='The response code for create server group with a server_id in bobby '
                          'resulted in {0}'.format(create_group_response.status_code))

    def test_create_group_with_invalid_server_id(self):
        """
        Create a server group in bobby with an invalid server_id, and verify the
        response code is 400.
        """
        create_group_response = self.bobby_client.create_server_group(
            group_id=self.group_id,
            server_id=87676876556,
            entity_id='TESTS')
        self.assertEquals(create_group_response.status_code, 400,
                          msg='The response code for create server group in bobby with invalid '
                          'serverID resulted in {0}'.format(create_group_response.status_code))
