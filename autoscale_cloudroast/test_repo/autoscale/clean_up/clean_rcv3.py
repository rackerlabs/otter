"""
Delete resources created during tests which may not have been cleaned up.
"""
from cafe.drivers.unittest.decorators import tags
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteAll(AutoscaleFixture):

    """
    Get list of groups/servers on account and delete them
    """

    @tags(type='group')
    def test_delete_groups_on_account(self):
        """
        Delete all groups on the account
        """
        list_groups_response = self.autoscale_client.list_scaling_groups()
        list_groups = (list_groups_response.entity).groups
        delete_count = 0
        for each_group in list_groups:
            print each_group.state['name']
            if "as_rcv3" in each_group.state['name']:
                self.empty_scaling_group(each_group)
                self.autoscale_client.delete_scaling_group(each_group.id)
                delete_count = delete_count + 1
        list_groups_again = ((self.autoscale_client.list_scaling_groups()).entity).groups
        print 'Deleting {0} groups, {1} still exist'.format(delete_count, len(list_groups_again))\
            if len(list_groups_again) is not 0 else "Deleted {0} groups".format(delete_count)


