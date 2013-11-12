"""
Test to create and verify the listing webhooks.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class ListWebhooks(ScalingGroupPolicyFixture):
    """
    Verify list webhooks
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with a policy and 3 webhooks on the policy
        """
        super(ListWebhooks, cls).setUpClass()
        webhook1_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook1').entity
        cls.webhook1 = cls.autoscale_behaviors.get_webhooks_properties(webhook1_response)
        webhook2_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook2').entity
        cls.webhook2 = cls.autoscale_behaviors.get_webhooks_properties(webhook2_response)
        webhook3_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook3').entity
        cls.webhook3 = cls.autoscale_behaviors.get_webhooks_properties(webhook3_response)

    def test_list_webhooks(self):
        """
        Verify the list webhooks call for response code 201, headers and data
        """
        list_webhooks_resp = self.autoscale_client.list_webhooks(self.group.id, self.policy['id'])
        self.assertEquals(list_webhooks_resp.status_code, 200,
                          msg='List webhooks returns response {0} for group'
                          ' {1}'.format(list_webhooks_resp.status_code, self.group.id))
        self.validate_headers(list_webhooks_resp.headers)
        webhook_id_list = [webhook.id for webhook in list_webhooks_resp.entity]
        self.assertTrue(self.webhook1['id'] in webhook_id_list)
        self.assertTrue(self.webhook2['id'] in webhook_id_list)
        self.assertTrue(self.webhook3['id'] in webhook_id_list)
