"""
Test to verify the pagination of a list of webhooks.
"""

from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class PaginateWebhooks(ScalingGroupWebhookFixture):
    """
    Verify pagination for list webhooks
    """

    def setUp(self):
        """
        Create three webhooks to use for testing
        """
        super(PaginateWebhooks, self).setUp()
        self._create_multiple_webhooks(3)
        self.total_webhooks = len((self.autoscale_client.list_webhooks().entity).webhooks)
        print self.total_webhooks
        # create three groups
        # don't need to add to resources since they will be deleted with the group

    def tearDown(self):
        """
        Delete the scaling group, policies, and webhooks
        """
        super(PaginateWebhooks, self).setUp()

    def test_list_webhooks_when_list_webhooks_is_greater_than_limit(self):
        """
        List the webhooks without a specified limit, and with a specified limit greater
        than the maximum of 100. Verify that the webhooks are listed in batches of the
        maximum limit with a next link.
        """
        self._create_multiple_webhooks(self.pagination_limit)
        params = [None, 10000]
        for each_param in params:
            list_webhooks = self._list_webhooks_with_given_limit(each_param)
            self._assert_list_webhooks_with_limits_next_link(self.pagination_limit,
                                                             list_webhooks)
            rem_list_webhooks = self.autoscale_client.list_webhooks(
                self.group.id, self.policy['id'], url=list_webhooks.webhooks_links.next).entity
            self._assert_list_webhooks_with_limits_next_link(1, rem_list_webhooks, False)
      # Test limit min clipping (anything lower than 1 produces 1 item)

    # Test limit == number of policies

    # Test limit < # of policies

    # Test limit greater than number of groups ( combine overage case params
        #[num_hooks+2, 99, 101, 1000])

    # Test invalid limits specified

    # Test list  with marker

    # Test list with invalid marker

    # Test that items on page 1 != items on page two

    # Test that total number created == total listed on all pages

    # Test that the number of items in the second batch == limit (# items > 2*limit)
    def _assert_list_webhooks_with_limits_next_link(self, expect_len, list_webhooks, next_link=True):
        """
        Asserts the length of the list group returned and the existence of its next link.
        If next_link is expected to be False, asserts that the webhooks_links is empty and does not
        have a next link.
        """
        self.assertGreaterEqual(len(list_webhooks.webhooks, expect_len))
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
        Create num_hooks number of webhooks on the scling policy that was
        created by the test fixture.
        """
        for _ in range(num_hooks):
            hook_name = "Webhook ", _
            self.autoscale_client.create_webhook(group_id=self.group.id,
                                                 policy_id=self.policy['id'],
                                                 name=hook_name)
