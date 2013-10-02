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
        for _ in range(4):
            group_response = cls.autoscale_behaviors.create_scaling_group_min()
            cls.group = group_response.entity
            cls.resources.add(
                cls.group.id, cls.autoscale_client.delete_scaling_group)

    def test_list_groups_with_limits(self):
        """
        List the scaling groups with the limit set to 3 and verify only
        3 groups are listed with the next link.
        """
        param = 3
        groups_response = self.autoscale_client.list_scaling_groups(limit=param)
        self.assertEquals(groups_response.status_code, 200, msg='list group failed')
        self.assertEquals(len((groups_response.entity).groups), param,
                          msg='The length of the list when limited to {0} was {1} '
                          'instead'.format(param, len((groups_response.entity).groups)))
