"""
Test to create and verify the created webhook
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class CreateWebhook(ScalingGroupWebhookFixture):

    """
    Verify create webhook
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a webhook with the given metadata
        """
        cls.wb_metadata = {'key': 'value'}
        super(CreateWebhook, cls).setUpClass(metadata=cls.wb_metadata)

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(CreateWebhook, cls).tearDownClass()

    def test_create_webhook(self):
        """
        Verify the create webhook call for response code, headers and data
        """
        self.assertEquals(self.create_webhook_response.status_code, 201,
                          msg='Create webhook for a policy failed with %s'
                          % self.create_webhook_response.status_code)
        self.validate_headers(self.create_webhook_response.headers)
        self.assertTrue(self.webhook['id'] is not None,
                        msg='Webhook id is None')
        self.assertTrue(self.webhook['links'] is not None,
                        msg="Newly created Webhook's links are null")
        self.assertEquals(self.webhook['name'], self.wb_name,
                          msg="Webhook's name does not match")
        self.assertEquals(
            self.autoscale_behaviors.to_data(self.webhook['metadata']),
            self.wb_metadata,
            msg="Webhook's metadata does not match %s" % self.wb_metadata)
