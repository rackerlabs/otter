"""
Test to verify pagination for a list of scaling policies.
"""
import unittest

from test_repo.autoscale.fixtures import AutoscaleFixture


class PolicyPaginationTest(AutoscaleFixture):

    """
    This class implements a set of test cases to verify pagination for a
    list of autoscale policies.
    """

    def setUp(self):
        """
        Create a new scaling group for each test case and create three policies on the group
        """
        super(PolicyPaginationTest, self).setUp()
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        self.group = create_resp.entity
        self.resources.add(self.group.id, self.autoscale_client.delete_scaling_group)
        self._create_multiple_scaling_policies(3)

    def test_list_policies_when_list_greater_than_default_limit(self):
        """
        Purpose:
        Verify the default/max limit for listing scaling policies.

        Preconditions:
        A scaling group to which policies can be added. (Provided by ScalingGroupPolicyFixture)

        Steps:
        For a group with a number of scaling policies greater than the
        default limit, list the policies without specifying a limit parameter,
        and specifying a limit greater than the default. Confirm that items are
        in batches of 'default limit' with a link to the next batch.
        Note: This test only checks for the first batch.
        """

        # There are already 3 policies from setUp
        self._create_multiple_scaling_policies(self.pagination_limit)
        params = [None, 100000]
        for each_param in params:
            list_policies = self._list_policies_with_given_limit(params)
            # check that at least (limit) items are listed, and a next link was provided
            self._assert_list_policies_with_limits_and_next_link(self.pagination_limit,
                                                                 list_policies)
            rem_list_policy =\
                self.autoscale_client.list_policies(self.group.id,
                                                    url=list_policies.policies_links.next).entity
            # Check that there is at least one policy on the next page
            self._assert_list_policies_with_limits_and_next_link(1, rem_list_policy, False)

    def test_list_policies_with_specified_limit_less_than_number_of_policies(self):
        """
        List the scaling policies with the limit set to be less than the number of groups
        on the tenant and verify groups are listed in batches of the limit specified.
        Verify the presence of a link to the next batch of scaling policies.
        """
        # Specify the limit to be one less than the current number of policies
        param = self.get_total_num_policies(self.group.id) - 1
        list_policies = self._list_policies_with_given_limit(param)
        self._assert_list_policies_with_limits_and_next_link(param, list_policies)
        rem_list_policy =\
            self.autoscale_client.list_policies(self.group.id,
                                                url=list_policies.policies_links.next).entity
        # Verify there is at least one item in the second batch, and no next link
        self._assert_list_policies_with_limits_and_next_link(1, rem_list_policy, False)

    @unittest.skip('AUTO-711')
    def test_list_policies_with_limit_equal_to_number_of_policies(self):
        """
        List the scaling policies with the limit set equal to the number of policies
        on the group, and verify all the policies are listed without a link for the
        next few policies.
        """
        param = self.get_total_num_policies(self.group.id)
        list_policies = self._list_policies_with_given_limit(param)
        self._assert_list_policies_with_limits_and_next_link(param, list_policies, False)

    def test_list_policies_with_invalid_limit(self):
        """
        List scaling policies with the limit set to invalid values and verify
        the message returned.
        """
        params = ['ab', '&', '3.0']
        for each_param in params:
            self._list_policies_with_given_limit(each_param, 400)

    def test_list_policies_with_limits_above_set_limit(self):
        """
        Verify that when the limit is set over the set limit (100), all policies
        up to 100 are returned with a link to the next page.
        Note Only 3 scaling policies are listed since the purpose of this test case is to ensure that
        the invalid limit does not produce an error The case to verify limiting of results to the
        maximum is handled in test_list_policies_when_list_greater_than_default_limit.
        """
        params = [101, 1000]
        num_policies = self.get_total_num_policies(self.group.id)
        for each_param in params:
            list_policies = self._list_policies_with_given_limit(each_param)
            self._assert_list_policies_with_limits_and_next_link(num_policies, list_policies, False)

    def test_list_policies_with_marker(self):
        """ List the scaling polices with the marker set to be a scaling policy id
        and verify.
        """
        policy = (self.autoscale_behaviors.create_policy_min(self.group.id))
        policies_response = self.autoscale_client.list_policies(self.group.id, marker=policy['id'])
        self.assertEquals(policies_response.status_code, 200, msg='list policies failed'
                          ' with {0}'.format(policies_response.status_code))

    def test_list_policies_with_invalid_marker(self):
        """
        List the scaling policies with invalid markers and verify.
        """
        params = [1, 'invalid', -13]
        for each_param in params:
            policies_response = self.autoscale_client.list_policies(self.group.id,
                                                                    marker=each_param)
            self.assertEquals(policies_response.status_code, 200, msg='list policies failed'
                              ' with {0}'.format(policies_response.status_code))

    def _assert_list_policies_with_limits_and_next_link(self, policy_len, list_policies,
                                                        next_link=True):
        """
        Asserts the length of the policies list, and whether the next link is present.
        Note: Given the current list_policies function, (which only lists the first page,
            there should be no way that the list is greater than the limit)
        If next_link is False, asserts that the policies_link is empty and does not have a
        next link.
        """
        self.assertGreaterEqual(len(list_policies.policies), policy_len)
        if next_link:
            self.assertTrue(hasattr(list_policies.policies_links, 'next'))
        else:
            self.assertDictEqual(list_policies.policies_links.links, {},
                                 msg='Links to next provided even when'
                                     ' there are no more groups to list')

    def _create_multiple_scaling_policies(self, num):
        """
        Creates 'num' number of scaling policies

        Note: For robust testing, polices should be a variety
        of types (webhook, schedule, etc.)

        Is there any reason the pagination could be different for different types?
        """
        for n in range(num):
            self.autoscale_behaviors.create_policy_given(self.group.id, sp_change=1)

    def _list_policies_with_given_limit(self, param, response=200):
        """
        Lists policies with the given limit and verifies that the response status_code
        was as expected.
        Note: Only the first page of results is returned
        """
        policies_response = self.autoscale_client.list_policies(self.group.id, limit=param)
        self.assertEquals(policies_response.status_code, response, msg='list policies failed'
                          'with {0}'.format(policies_response.status_code))
        return policies_response.entity
