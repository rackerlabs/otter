"""
Test to create and verify the listing webhooks.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class ListWebhookManifest(ScalingGroupPolicyFixture):
    """
    Verify that the webhook manifest is provided when using /groups/[group_id]?webhooks=True
    Note: Should "webhooks" be case sensitive (currently it is)
    Note: Should "True" be case sensitive (currently it is not)
    (Assume that pagination of policies is the same)
    What is the pagination behavior?
    Test - add a second policy with no webhooks, verify empty list in webhooks, and

    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with a policy and 3 webhooks on the policy
        """
        super(ListWebhookManifest, cls).setUpClass()
        webhook1_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook1').entity
        cls.webhook1 = cls.autoscale_behaviors.get_webhooks_properties(webhook1_response)
        webhook2_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook2').entity
        cls.webhook2 = cls.autoscale_behaviors.get_webhooks_properties(webhook2_response)
        webhook3_response = cls.autoscale_client.create_webhook(
            cls.group.id, cls.policy['id'], 'webhook3').entity
        cls.webhook3 = cls.autoscale_behaviors.get_webhooks_properties(webhook3_response)

    def test_manifest_webhooks(self):
        """
        Verify the manifest call for response code 200, headers and data
        """
        params = ["true", "tRuE"]
        for param in params:
            list_manifest_resp = \
                self.autoscale_client.view_manifest_config_for_scaling_group_with_webhooks(
                    self.group.id,
                    webhooks=param)
            list_manifest = list_manifest_resp.entity
            self.assertEquals(list_manifest_resp.status_code, 200,
                              msg='List scaling group manifest returns response {0} for group'
                              ' {1}'.format(list_manifest_resp.status_code, self.group.id))
            self.validate_headers(list_manifest_resp.headers)
            policy_ids = []
            for policy in list_manifest.scalingPolicies:
                policy_ids.append(policy.id)
            self.assertEqual(list_manifest.scalingPolicies[0].id, self.policy['id'],
                             msg='Policy id in manifest did not match expected policy '
                             '{0}'.format(self.policy['id']))
            self.assertEqual(list_manifest.id, self.group.id,
                             msg='Group id did not match for group '
                             '{0}'.format(self.first_scaling_group.id))
            self.assert_group_state(list_manifest.state)
            webhook_id_list = [webhook.id for webhook in list_manifest.scalingPolicies[0].webhooks]
            self.assertTrue(self.webhook1['id'] in webhook_id_list)
            self.assertTrue(self.webhook2['id'] in webhook_id_list)
            self.assertTrue(self.webhook3['id'] in webhook_id_list)

    def test_manifest_webhooks_invalid(self):
        """
        Verify that the manifest is not displayed in the following scenarios:
            1.) List group request (/groups/<group_id) is made without the query parameter webhooks=True
            2.) Query parameter "webhooks" uses incorrect case
            3.) Query parameter "webhooks" is provided an invalid value
        """
        params = [None, "False", 15, "Tr@%"]
        for param in params:
            list_manifest_resp = \
                self.autoscale_client.view_manifest_config_for_scaling_group_with_webhooks(
                    self.group.id,
                    webhooks=param)
            list_manifest = list_manifest_resp.entity
            self.assertEquals(list_manifest_resp.status_code, 200,
                              msg='List scaling group manifest returns response {0} for group'
                              ' {1}'.format(list_manifest_resp.status_code, self.group.id))
            self.assertFalse(hasattr(list_manifest.scalingPolicies, 'webhooks'))
            self.assertFalse(hasattr(list_manifest.scalingPolicies, 'webhook_links'))
