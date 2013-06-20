"""
Test to verify update webhook.
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class UpdateWebhook(ScalingGroupWebhookFixture):
    """
    Verify update webhook
    """

    @classmethod
    def setUpClass(cls):
        """
        Create scaling group with webhook with metadata.
        """
        cls.metadata = {'hello': 'world'}
        super(UpdateWebhook, cls).setUpClass(metadata=cls.metadata)

    @classmethod
    def tearDownClass(cls):
        """
        Delete scaling group.
        """
        super(UpdateWebhook, cls).tearDownClass()

    def test_update_webhook_name_only(self):
        """
        Update webhook with only name in the request and verify.
        """
        upd_wb_name = 'updated_wb_name'
        update_webhook_response = self.autoscale_client.update_webhook(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            webhook_id=self.webhook['id'],
            name=upd_wb_name)
        self.assertEquals(update_webhook_response.status_code, 400,
                          msg='Update webhook passed with with incomplete requests: {0}'
                          .format(update_webhook_response.status_code))

    def test_update_webhook_successfully(self):
        """
        Update webhook with full request and verify.
        """
        upd_metadata = {'hello': 'sfo'}
        upd_name = "updated_wb"
        update_webhook_response = self.autoscale_client.update_webhook(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            webhook_id=self.webhook['id'],
            name=upd_name,
            metadata=upd_metadata
        )
        get_webhook_response = self.autoscale_client.get_webhook(self.group.id,
                                                                 self.policy[
                                                                     'id'],
                                                                 self.webhook['id'])
        updated_webhook = get_webhook_response.entity
        self.assertEquals(update_webhook_response.status_code, 204,
                          msg='Update webhook failed with {0}'
                          .format(update_webhook_response.status_code))
        self.assertTrue(update_webhook_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(update_webhook_response.headers)
        self.assertEquals(updated_webhook.id, self.webhook['id'],
                          msg='Webhook Id is not as expected after the update')
        self.assertEquals(updated_webhook.links, self.webhook['links'],
                          msg='Links for the webhook is not as expected after the update')
        self.assertEquals(updated_webhook.name, upd_name,
                          msg='Name of the webhook did not update')
        self.assertEquals(
            self.autoscale_behaviors.to_data(updated_webhook.metadata),
            upd_metadata,
            msg='Metadata of the webhook did not update')

    def test_update_webhook_without_metadata_successfully(self):
        """
        Update webhook with only name in the request without metadata and verify.
        """
        create_webhook = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_webhook.entity)
        update_webhook_response = self.autoscale_client.update_webhook(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            webhook_id=webhook['id'],
            name=self.wb_name
        )
        self.assertEquals(update_webhook_response.status_code, 400,
                          msg='Update webhook was successful with incomplete request: {0}'
                          .format(update_webhook_response.status_code))
