"""
Test the bobby links in the response objects
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name
import unittest


@unittest.skip('AUTO-553')
class BobbyLinksTest(BobbyFixture):

    """
    Verify the links provided in the reponse objects
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a bobby group, bobby server group and policy group
        """
        super(BobbyLinksTest, cls).setUpClass()
        cls.group_id = rand_name('TEST-GROUP-LINKS-78f3-4543-85bc1')
        cls.server_id = rand_name('TEST-SERVER-GROUP-LINKS-78f3-4543-85bc1')
        cls.policy_id = rand_name('TEST-POLICY-LINKS-78f3-4543-85bc1')
        cls.group = cls.bobby_behaviors.create_bobby_group_given(
            group_id=cls.group_id)
        cls.server_group = cls.bobby_behaviors.create_bobby_server_group_given(
            group_id=cls.group_id,
            server_id=cls.server_id)
        cls.bobby_policy = cls.bobby_behaviors.create_bobby_policy_given(
            group_id=cls.group_id,
            policy_id=cls.policy_id)

    def test_create_group_response_links(self):
        """
        Create a group in bobby with a given group_id, notification
        and notification pals, and verify the links in the response object.
        Note : Has no version
        """
        self._verify_links(self.group)
        self._verify_get_on_link(self.group, 'group')

    def test_get_group_links(self):
        """
        Get a group, and verify its links and verify a GET using the link
        returns 200
        """
        get_group = self.bobby_client.get_group(self.group_id).entity
        self._verify_links(get_group)
        self._verify_get_on_link(get_group, 'group')

    def test_create_server_group_response_links(self):
        """
        Create a server group in bobby with a given server_id
        and verify the links in the response object.
        Note : Has no version
        """
        self._verify_links(self.server_group.entity, self.server_id)
        self._verify_get_on_link(self.server_group.entity, 'server_group')

    def test_get_server_group_links(self):
        """
        Get a server group, and verify its links and verify a GET using the link
        returns 200
        """
        get_server_group = self.bobby_client.get_server_group(
            self.group_id, self.server_id).entity
        self._verify_links(get_server_group)
        self._verify_get_on_link(get_server_group, 'server_group')

    def test_create_bobby_policy_response_links(self):
        """
        Create a bobby policy in bobby with a given policy_id
        and verify the links in the response object.
        Note : Has no version
        """
        self._verify_links(self.bobby_policy.entity, self.policy_id)
        self._verify_get_on_link(self.bobby_policy.entity, 'bobby_policy')

    def test_get_bobby_policy_links(self):
        """
        Get a bobby policy, and verify its links and verify a GET using the link
        returns 200
        """
        get_bobby_policy = self.bobby_client.get_bobby_policy(
            self.group_id, self.policy_id).entity
        self._verify_links(get_bobby_policy)
        self._verify_get_on_link(get_bobby_policy, 'bobby_policy')

    @unittest.skip('AUTO-555')
    def test_trailing_slash_in_links(self):
        """
        Get a bobby policy with a trialing slash in the link, and verify its
        returns 200
        """
        get_bobby_policy = self.bobby_client.get_bobby_policy(
            self.group_id, self.policy_id).entity
        get_response = self.bobby_client.get_bobby_policy(
            get_bobby_policy.links.self + '/', None)
        self.assertEquals(get_response.status_code, 200,
                          msg='Get bobby policy failed with {0} when the link had a'
                          ' trailing slash'.format(get_response))

    def _verify_links(self, response_obj, obj_id=None):
        """
        verify the links are as expected and a GET on the links returns a 200
        """
        obj_id = obj_id or self.group_id
        self.assertTrue(response_obj.links is not None,
                        msg='No links returned upon group creation in bobby')
        self.assertTrue(obj_id in response_obj.links.self,
                        msg='The ID does not exist in self links')
        self.assertTrue(self.url in response_obj.links.self,
                        msg='The url used to create {0} doesnt match'
                        ' the url in self link {1}'.format(self.url, response_obj.links.self))

    def _verify_get_on_link(self, response_obj, bobby_type=None):
        if bobby_type is 'group':
            get_response = self.bobby_client.get_group(response_obj.links.self)
        if bobby_type is 'server_group':
            get_response = self.bobby_client.get_server_group(
                response_obj.links.self, None)
        if bobby_type is 'bobby_policy':
            get_response = self.bobby_client.get_bobby_policy(
                response_obj.links.self, None)
        self.assertEquals(get_response.status_code, 200,
                          msg="Get failed with {0} when the link from"
                          " the get's response is used".format(get_response.status_code))
