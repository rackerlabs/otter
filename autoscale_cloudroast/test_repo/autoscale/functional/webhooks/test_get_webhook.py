"""
Test to verify get webhook.
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class GetWebhook(ScalingGroupWebhookFixture):
    """
    Verify get webhook
    """

    @classmethod
    def setUpClass(cls):
        """
        Create scaling group with webhook.
        """
        cls.wb_metadata = {'key': 'value'}
        super(GetWebhook, cls).setUpClass(metadata=cls.wb_metadata)
        cls.get_webhook_response = cls.autoscale_client.get_webhook(
            cls.group.id,
            cls.policy[
                'id'],
            cls.webhook['id'])
        cls.get_webhook = cls.get_webhook_response.entity

    def test_get_webhook(self):
        """
        Get a webhook and verify response code 200, headers and the data.
        """
        self.assertEquals(self.get_webhook_response.status_code, 200,
                          msg='Get webhook failed with {0}'
                          .format(self.get_webhook_response.status_code))
        self.validate_headers(self.get_webhook_response.headers)
        self.assertEquals(self.get_webhook.id, self.webhook['id'],
                          msg='Webhook Id is null')
        self.assertEquals(self.get_webhook.links, self.webhook['links'],
                          msg='Links for the webhook is null')
        self.assertEquals(self.get_webhook.name, self.wb_name,
                          msg='Name of the webhook did not match')
        self.assertEquals(
            self.autoscale_behaviors.to_data(self.get_webhook.metadata),
            self.wb_metadata,
            msg='Metadata of the webhook did not match')
