"""
Test to verify pagination for a list of groups.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class GroupPaginationTest(AutoscaleFixture):

    """
    Verify pagination for list group.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create 10 scaling groups.
        """
        super(GroupPaginationTest, cls).setUpClass()
        num_groups = 4
        for _ in range(num_groups):
            group_response = cls.autoscale_behaviors.create_scaling_group_min()
            cls.group = group_response.entity
            cls.resources.add(
                cls.group.id, cls.autoscale_client.delete_scaling_group)
        cls.total_groups = len((cls.autoscale_client.list_scaling_groups().entity).groups)

    def test_list_groups_with_limit_less_than_number_of_groups(self):
        """
        List the scaling groups with the limit set to be less than number of groups
        on the tenant and verify groups are listed in batches of the limit specified
        with a link for the next few groups.
        """
        param = self.total_groups - 1
        groups_response = self.autoscale_client.list_scaling_groups(limit=param)
        self.assertEquals(groups_response.status_code, 200, msg='list group failed')
        self.assertEquals(len((groups_response.entity).groups), param,
                          msg='The length of the list when limited to {0} was {1} '
                          'instead'.format(param, len((groups_response.entity).groups)))

    def test_list_groups_with_limit_equal_to_number_of_groups(self):
        """
        List the scaling groups with the limit set to be equal to the number of groups
        on the tenant and verify all the groups are listed without a link for the next
        few groups.
        """
        param = self.total_groups
        groups_response = self.autoscale_client.list_scaling_groups(limit=param)
        self.assertEquals(groups_response.status_code, 200, msg='list group failed')
        self.assertEquals(len((groups_response.entity).groups), param,
                          msg='The length of the list when limited to {0} was {1} '
                          'instead'.format(param, len((groups_response.entity).groups)))

    def test_list_groups_with_limit_greater_than_number_of_groups(self):
        """
        List the scaling groups with the limit set to be greater than the number of groups
        on the tenant and verify all the groups are listed without a link for the next
        few groups.
        """
        param = self.total_groups + 2
        groups_response = self.autoscale_client.list_scaling_groups(limit=param)
        self.assertEquals(groups_response.status_code, 200, msg='list group failed')
        self.assertEquals(len((groups_response.entity).groups), self.total_groups,
                          msg='The length of the list when limited to {0} was {1} '
                          'instead'.format(self.total_groups, len((groups_response.entity).groups)))
