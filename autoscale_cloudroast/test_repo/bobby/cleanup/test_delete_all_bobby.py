"""
Deletes.
"""
from cafe.drivers.unittest.decorators import tags
from test_repo.bobby.fixtures import BobbyFixture


class DeleteAll(BobbyFixture):

    """
    Get list of groups on account and delete them from bobby
    """

    @tags(type='bobbygroups')
    def test_delete_all_groups_in_bobby_for_account(self):
        """
        Delete all groups on the account from bobby
        """
        list_groups = self.bobby_client.list_groups().entity
        for each_group in list_groups:
            self.bobby_client.delete_group(each_group.groupId)
        list_groups_again = (self.bobby_client.list_groups()).entity
        print 'Deleting {0} groups, {1} still exist'.format(len(list_groups), len(list_groups_again))\
            if len(list_groups_again) is not 0 else "Deleted {0} groups".format(len(list_groups))
