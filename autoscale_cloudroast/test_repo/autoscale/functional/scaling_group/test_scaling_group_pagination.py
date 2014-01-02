"""
Test to verify pagination for a list of groups.
@TODO: Tests for marker not included
"""
import unittest

from test_repo.autoscale.fixtures import AutoscaleFixture


class GroupPaginationTest(AutoscaleFixture):

    """
    Verify pagination for list group.
    """

    def setUp(self):
        """
        Create 3 scaling groups.
        """
        super(GroupPaginationTest, self).setUp()
        self._create_multiple_groups(3)

    def tearDown(self):
        """
        Delete the scaling groups.
        """
        super(GroupPaginationTest, self).tearDown()
        self.resources.release()

    def test_list_groups_when_list_groups_is_greater_than_the_limit(self):
        """
        List the scaling groups without limit and limit over 100 when over 100
        groups exist on the group and verify the groups are listed in batches
        of the set limit with a next link.
        """
        self._create_multiple_groups(self.pagination_limit)
        params = [None, 100000]
        for each_param in params:
            list_groups = self._list_group_with_given_limit(each_param)
            self._assert_list_groups_with_limits_and_next_link(self.pagination_limit,
                                                               list_groups)
            rem_list_group = self.autoscale_client.list_scaling_groups(
                list_groups.groups_links.next).entity
            self._assert_list_groups_with_limits_and_next_link(1, rem_list_group, False)

    def test_list_groups_with_limit_less_than_number_of_groups(self):
        """
        List the scaling groups with the limit set to be less than number of groups
        on the tenant and verify groups are listed in batches of the limit specified
        with a link for the next few groups.
        """
        param = self.get_total_num_groups() - 1
        list_group = self._list_group_with_given_limit(param)
        self._assert_list_groups_with_limits_and_next_link(param, list_group)
        rem_list_group = self.autoscale_client.list_scaling_groups(
            list_group.groups_links.next).entity
        self._assert_list_groups_with_limits_and_next_link(1, rem_list_group, False)

    @unittest.skip('AUTO-711')
    def test_list_groups_with_limit_equal_to_number_of_groups(self):
        """
        List the scaling groups with the limit set to be equal to the number of groups
        on the tenant and verify all the groups are listed without a link for the next
        few groups.
        """
        param = self.get_total_num_groups()
        list_groups = self._list_group_with_given_limit(param)
        self._assert_list_groups_with_limits_and_next_link(param, list_groups, False)

    def test_list_groups_with_limit_greater_than_number_of_groups(self):
        """
        List the scaling groups with the limit set to be greater than the number of groups
        on the tenant and verify all the groups are listed without a link for the next
        few groups.
        """
        total_groups = self.get_total_num_groups()
        param = total_groups + 2
        list_groups = self._list_group_with_given_limit(param)
        self._assert_list_groups_with_limits_and_next_link(total_groups, list_groups, False)

    def test_list_groups_with_invalid_limits(self):
        """
        List scaling groups with limit set to invalid values and verify the message returned
        """
        params = ['ab', '&']
        for each_param in params:
            self._list_group_with_given_limit(each_param, 400)

    def test_list_groups_with_limits_below_set_limit(self):
        """
        Verify that when the limit is below the set limit(1), one group is
        listed.
        """
        params = [0, -1]
        for each_param in params:
            list_groups = self._list_group_with_given_limit(each_param, 200)
            self._assert_list_groups_with_limits_and_next_link(1, list_groups)

    def test_list_groups_with_limits_above_set_limit(self):
        """
        Verify when the limit is over the set limit(100), all groups upto a 100
        are returned
        """
        total_groups = self.get_total_num_groups()
        params = [101, 1000]
        for each_param in params:
            list_groups = self._list_group_with_given_limit(each_param, 200)
            self._assert_list_groups_with_limits_and_next_link(total_groups, list_groups, False)

    def test_list_groups_with_marker(self):
        """
        List the scaling groups with the marker set to be a group ID
        on the tenant and verify.
        """
        group = (self.autoscale_behaviors.create_scaling_group_min()).entity
        groups_response = self.autoscale_client.list_scaling_groups(marker=group.id)
        self.assertEquals(groups_response.status_code, 200, msg='list group failed'
                          ' with {0}'.format(groups_response.status_code))

    def test_list_groups_with_invalid_marker(self):
        """
        List the scaling groups with invalid markers and verify.
        (Currently Otter is not checking the validity of the marker)
        """
        params = [1, 'invalid']
        for each_param in params:
            groups_response = self.autoscale_client.list_scaling_groups(marker=each_param)
            self.assertEquals(groups_response.status_code, 200, msg='list group failed'
                              ' with {0}'.format(groups_response.status_code))

    def _list_group_with_given_limit(self, param, response=200):
        """
        Lists groups with given limit and verifies they are successful
        """
        groups_response = self.autoscale_client.list_scaling_groups(
            limit=param)
        self.assertEquals(groups_response.status_code, response, msg='list group failed'
                          ' with {0}'.format(groups_response.status_code))
        return groups_response.entity

    def _assert_list_groups_with_limits_and_next_link(self, group_len, list_group, next_link=True):
        """
        Asserts the length of the list group returned and its groups links.
        If next_link is False, asserts that the group_links is empty and does not have a next link
        """
        self.assertGreaterEqual(len(list_group.groups), group_len)
        if next_link:
            self.assertTrue(hasattr(list_group.groups_links, 'next'))
        else:
            self.assertDictEqual(list_group.groups_links.links, {}, msg='Links to next provided'
                                 ' even when there are no more groups to list')

    def _create_multiple_groups(self, num):
        """
        Creates 'num' number of groups
        """
        for _ in range(num):
            group_response = self.autoscale_behaviors.create_scaling_group_min()
            self.group = group_response.entity
            self.resources.add(self.group.id, self.autoscale_client.delete_scaling_group)
