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
        Creates a scaling group with a webhook, with the given metadata
        """
        cls.wb_metadata = {'key': 'value'}
        super(CreateWebhook, cls).setUpClass(metadata=cls.wb_metadata)

    def test_create_webhook(self):
        """
        Verify the create webhook call for response code 201, headers and data
        """
        self.assertEquals(self.create_webhook_response.status_code, 201,
                          msg='Create webhook for a policy failed with {0} for group'
                          ' {1}'.format(self.create_webhook_response.status_code,
                                        self.group.id))
        self.validate_headers(self.create_webhook_response.headers)
        self.assertTrue(self.webhook['id'] is not None,
                        msg='Webhook id is None for group {0}'.format(self.group.id))
        self.assertTrue(self.webhook['links'] is not None,
                        msg="Newly created Webhook's links are null for group "
                        "{0}".format(self.group.id))
        self.assertEquals(self.webhook['name'], self.wb_name,
                          msg="Webhook's name does not match for group {0}".format(self.group.id))
        self.assertEquals(
            self.autoscale_behaviors.to_data(self.webhook['metadata']),
            self.wb_metadata,
            msg="Webhook's metadata does not match {0} for group"
            ' {1}'.format(self.wb_metadata, self.group.id))
