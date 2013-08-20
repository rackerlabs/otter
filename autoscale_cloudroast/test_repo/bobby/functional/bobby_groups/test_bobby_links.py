"""
Test the bobby links in the response objects
"""
from test_repo.bobby.fixtures import BobbyGroupFixture


class BobbyLinksTest(BobbyGroupFixture):

    """
    Verify the links provided in the reponse objects
    """

    def test_create_group_response_links(self):
        """
        Create a group in bobby with a given group_id, notification
        and notification pals, and verify the links in the response object.
        Note : Has no version
        """
        self.assertTrue(self.group.links is not None,
                        msg='No links returned upon group creation in bobby')
        self.assertTrue(self.group_id in self.group.links.self,
                        msg='The ID does not exist in self links')
        self.assertTrue(self.url in self.group.links.self,
                        msg='The url used to create the group {0} doesnt match'
                        ' the url in self link {1}'.format(self.url, self.group.links.self))
        get_group_resp = self.bobby_client.\
            get_group(self.group.links.self)
        self.assertEquals(get_group_resp.status_code, 200,
            msg="Get group is bobby failed with {0} when the link from"
            " the create's response is used".format(get_group_resp.status_code))

    def test_get_group_links(self):
        """
        Get a group, and verify its links and verify a GET using the link
        returns 200
        """
        get_group = self.bobby_client.get_group(self.group_id).entity
        self.assertTrue(get_group.links is not None,
                        msg='No links returned upon group creation in bobby')
        self.assertTrue(self.group_id in get_group.links.self,
                        msg='The ID does not exist in self links')
        self.assertTrue(self.url in get_group.links.self,
                        msg='The url used to create the group {0} doesnt match'
                        ' the url in self link {1}'.format(self.url, get_group.links.self))
        get_group_resp = self.bobby_client.get_group(get_group.links.self)
        self.assertEquals(get_group_resp.status_code, 200,
            msg="Get group is bobby failed with {0} when the link from"
            " the get's response is used".format(get_group_resp.status_code))

