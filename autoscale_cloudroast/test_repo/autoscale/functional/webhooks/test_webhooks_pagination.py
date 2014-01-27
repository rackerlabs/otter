"""
Test to verify the pagination of a list of webhooks.
"""
import unittest

from test_repo.autoscale.fixtures import AutoscaleFixture


class PaginateWebhooks(AutoscaleFixture):
    """
    Verify pagination for list webhooks
    """

    @classmethod
    def setUpClass(cls):
        """
        Initialize autoscale configs, behaviors and client
        """
        super(PaginateWebhooks, cls).setUpClass()
        cls.limits_response = cls.autoscale_client.view_limits().entity
        cls.max_webhooks = cls.limits_response.absolute.maxWebhooksPerPolicy

    def setUp(self):
        """
        Create a group, a scaling policy, and four webhooks for testing since no webhook is supplied
        by the fixture. A new group is created for each test case, and the group is deleted
        upon test completion, which will also delete the associated policy and webhooks.
        """
        super(PaginateWebhooks, self).setUp()
        group_response = self.autoscale_behaviors.create_scaling_group_min()
        self.group = group_response.entity
        self.resources.add(self.group.id, self.autoscale_client.delete_scaling_group)
        self.policy = self.autoscale_behaviors.create_policy_given(self.group.id, sp_change=1)
        self._create_multiple_webhooks(4)

    def test_list_webhooks_when_list_webhooks_is_greater_than_default_limit(self):
        """
        List the webhooks without a specified limit, and with a specified limit greater
        than the maximum of 100. Verify that the webhooks are listed in batches of the
        maximum limit (100) with a next link.
        """
        to_build = self.max_policies - self.get_total_num_webhooks(self.group.id, self.policy['id'])
        self._create_multiple_webhooks(to_build)
        params = [None, 10000]
        for each_param in params:
            list_webhooks = self._list_webhooks_with_given_limit(each_param)
            self._assert_list_webhooks_with_limits_next_link(self.max_webhooks,
                                                             list_webhooks, False)

    def test_list_webhooks_with_specified_limit_less_than_number_of_policies(self):
        """
        List the webhooks with the limit set to be less than the number of webhooks on the policy.
        Verify that the webhooks are listed in batches of the specifed limit, and that a link to
        the next batch exists.
        """
        # Specify the limit to be one less than the current number of webhooks (4 were created in setUp)
        total_webhooks = self.get_total_num_webhooks(self.group.id, self.policy['id'])
        param = total_webhooks - 1
        list_webhooks = self._list_webhooks_with_given_limit(param)
        self._assert_list_webhooks_with_limits_next_link(param, list_webhooks)
        rem_list_webhooks = self.autoscale_client.list_webhooks(
            self.group.id, self.policy['id'], url=list_webhooks.webhooks_links.next).entity
        #Verify that there is at least one webhook in the second batch and there is no next link
        self._assert_list_webhooks_with_limits_next_link(1, rem_list_webhooks, False)

    @unittest.skip('AUTO-711')
    def test_list_webhooks_with_limit_equal_to_number_of_webhooks(self):
        """
        List the webhooks with the limit set equal to the number of existing webhooks.
        Verify all the webhooks are listed and there is no next link to a second page.
        """
        param = self.get_total_num_webhooks(self.group.id, self.policy['id'])
        list_webhooks = self._list_webhooks_with_given_limit(param)
        self._assert_list_webhooks_with_limits_next_link(param, list_webhooks, False)

    def test_list_webhooks_with_invalid_limit(self):
        """
        List webhooks with a limit set to an invalid value. Verify that the
        response indicates the request failed (400).
        """
        params = ['ab', '&', 3.0]
        for each_param in params:
            self._list_webhooks_with_given_limit(each_param, 400)

    def test_list_webhooks_with_limit_set_above_valid_limit(self):
        """
        Verify that when the limit is specified over the set limit (100), all webhooks up to 100
        are returned. There should be no next link since there are less than max limit webhooks.
        Note that only 4 webhooks are listed since the purpose of this test case is to ensure that
        the invalid limit does not produce an error. The case to verify limiting of results to the
        maximum is handled in test_list_webhooks_when_list_webhooks_is_greater_than_default_limit.
        """
        params = [101, 1000]
        num_hooks = self.get_total_num_webhooks(self.group.id, self.policy['id'])
        for each_param in params:
            list_webhooks = self._list_webhooks_with_given_limit(each_param)
            self._assert_list_webhooks_with_limits_next_link(num_hooks, list_webhooks, False)

    def test_list_webhooks_with_marker(self):
        """
        List the webhooks with the marker set to be an existing webhook id and verify that the correct
        response (200) is recieved.
        """
        # Create a webhook in order to use the id as a marker
        create_webhook = self.autoscale_client.create_webhook(group_id=self.group.id,
                                                              policy_id=self.policy['id'],
                                                              name="Marker test").entity
        webhook = self.autoscale_behaviors.get_webhooks_properties(create_webhook)
        # List the webhooks with a specified marker
        webhook_response = self.autoscale_client.list_webhooks(self.group.id, self.policy['id'],
                                                               marker=webhook['id'])
        self.assertEquals(webhook_response.status_code, 200,
                          msg='list webhooks failed with {0}'.format(webhook_response.status_code))

    def test_list_webhooks_with_invalid_marker(self):
        """
        List the webhooks with invalid markers and verify that the marker is ignored.
        Currently Otter is not checking the validity of a marker, so the expected behavior is
        that the invalid marker is ignored.
        """
        params = [1, 'invalid']
        for each_param in params:
            webhook_response = self.autoscale_client.list_webhooks(self.group.id, self.policy['id'],
                                                                   marker=each_param)
            self.assertEquals(webhook_response.status_code, 200, msg='list webhooks failed'
                              'with {0}'.format(webhook_response.status_code))

    def _assert_list_webhooks_with_limits_next_link(self, expect_len, list_webhooks, next_link=True):
        """
        Asserts that the length of the webhooks list is greater than or equal to the exptected length,
        and the existence of its next link.
        If next_link is expected to be False, asserts that webhooks_links is empty and does not
        have a next link.
        """
        self.assertGreaterEqual(len(list_webhooks.webhooks), expect_len)
        if next_link:
            self.assertTrue(list_webhooks.webhooks_links.next)
        else:
            self.assertDictEqual(list_webhooks.webhooks_links.links, {}, msg='Links to next provided'
                                 ' when not expected')

    def _list_webhooks_with_given_limit(self, param, response=200):
        """
        Lists webhooks with the limit given in param and verifies the expected
        response code.
        """
        webhook_response = self.autoscale_client.list_webhooks(self.group.id, self.policy['id'],
                                                               limit=param)
        self.assertEquals(webhook_response.status_code, response, msg='List webhooks returned'
                          'with unexpected response: {0}'.format(webhook_response.status_code))
        return webhook_response.entity

    def _create_multiple_webhooks(self, num_hooks):
        """
        Create num_hooks number of webhooks on the scaling policy that was
        created during setup.
        """
        for _ in range(num_hooks):
            hook_name = "Webhook " + str(_)
            self.autoscale_client.create_webhook(group_id=self.group.id,
                                                 policy_id=self.policy['id'],
                                                 name=hook_name)
