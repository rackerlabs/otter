"""
Test the bobby links in the response objects
"""
from test_repo.bobby.fixtures import BobbyGroupFixture


class BobbyLinksTest(BobbyGroupFixture):

    """
    Verify GET and DELETE on the links provided in all the apiu reponse objects
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a group with the given group id
        """
        super(BobbyLinksTest, cls).setUpClass()


    def test_create_group_response_links(self):
        """
        Create a group in bobby with a given group_id, notification
        and notification pals, and verify the links in the response object.
        Note : Has no version
        """
        group = self.bobby_client.create_group(
            group_id=self.group_id,
            notification=self.notification,
            notification_plan=self.notification_plan).entity
        self.assertTrue(group.links is not None,
                        msg='No links returned upon group creation in bobby')
        self.assertTrue(self.group_id in group.links.self,
                        msg='The ID does not exist in self links')
        self.assertTrue(self.url in group.links.self,
                        msg='The url used to create the group {0} doesnt match'
                        ' the url in self link {1}'.format(self.url, group.links.self))
        get_group_resp = self.bobby_client.\
            get_group(group.links.self)
        self.assertEquals(get_group_resp.status_code, 200,
            msg="Get group is bobby failed with {0} when the link from"
            " the create's response is used".format(get_group_resp.status_code))
        self.assertEqual(self.group.id, get_group_resp.entity.id)
        self.resources.add(self.group_id,
                           self.bobby_client.delete_group)

    def test_get_group_links(self):
        """
        Get a group, and verify its links.
        """
        self.assertTrue(self.group.links is not None,
                        msg='No links returned upon group creation in bobby')
        self.assertTrue(self.group_id_temp in self.group.links.self,
                        msg='The ID does not exist in self links')
        self.assertTrue(self.url in self.group.links.self,
                        msg='The url used to create the group {0} doesnt match'
                        ' the url in self link {1}'.format(self.url, self.group.links.self))
        get_group_resp = self.bobby_client.\
            get_group(self.group.links.self)
        self.assertEquals(get_group_resp.status_code, 200,
            msg="Get group is bobby failed with {0} when the link from"
            " the create's response is used".format(get_group_resp.status_code))
        self.assertEqual(self.group.id, get_group_resp.entity.id)
