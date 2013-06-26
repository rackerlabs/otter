"""
Test to verify the links on the autoscaling api responses.
"""
import re
from urlparse import urlparse
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class AutoscalingLinksTest(ScalingGroupWebhookFixture):
    """
    Verify links on the autoscaling api response calls
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with webhook
        """
        super(AutoscalingLinksTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(AutoscalingLinksTest, cls).tearDownClass()

    def test_scaling_group_links(self):
        """
        Verify that scaling groups has links for self
        (no bookmark link)
        """
        self.assertTrue(self.group.links is not None,
                        msg='No links returned upon scaling group creation')
        #Issue AUTO-209
        # self.assertTrue(self.group.id in self.group.links.bookmark,
        #                 msg='The Group ID does not exit in the Links')
        self.assertTrue(self.group.id in self.group.links.self,
                        msg='The Group ID does not exit in the Links')

    def test_scaling_group_self_link(self):
        """
        Verify that scaling groups self link is a full url with a version
        """
        group_self_link = self.group.links.self
        self.assertTrue(self._has_version(group_self_link))
        get_group_resp = self.autoscale_client.\
            view_manifest_config_for_scaling_group(group_self_link)
        self.assertEqual(self.group.id, get_group_resp.entity.id)

    def test_scaling_policy_links(self):
        """
        Verify that scaling policy has links for self
        """
        policy_links = self.policy['links']
        self.assertTrue(self.policy['links'] is not None,
                        msg='No links returned upon scaling policy creation')
        #Issue AUTO-209
        # self.assertTrue(self.policy['id'] in policy_links.bookmark,
        #                 msg='The Policy ID does not exit in the Links')
        self.assertTrue(self.policy['id'] in policy_links.self,
                        msg='The Policy ID does not exit in the Links')

    def test_scaling_policy_self_link(self):
        """
        Verify that scaling policy self link is a full url with a version
        """
        policy_self_link = self.policy['links'].self
        self.assertTrue(self._has_version(policy_self_link))
        get_policy_resp = self.autoscale_client.get_policy_details(
            self.group.id, policy_self_link)
        self.assertEqual(self.policy['id'], (get_policy_resp.entity).id)

    def test_webhook_links(self):
        """
        Verify that webhook has links for self
        """
        webhook_links = self.webhook['links']
        self.assertTrue(self.webhook['links'] is not None,
                        msg='No links returned upon webhook creation')
        #Issue AUTO-209
        # self.assertTrue(self.webhook['id'] in webhook_links.bookmark,
        #                 msg='The webhook ID does not exit in the Links')
        self.assertTrue(self.webhook['id'] in webhook_links.self,
                        msg='The webhook ID does not exit in the Links')

    def test_webhook_self_link(self):
        """
        Verify that webhooks self link is a full url with a version
        """
        webhook_self_link = self.webhook['links'].self
        self.assertTrue(self._has_version(webhook_self_link))
        get_webhook_resp = self.autoscale_client.get_webhook(
            self.group.id, self.policy['id'], webhook_self_link)
        self.assertEqual(self.webhook['id'], (get_webhook_resp.entity).id)

    def test_webhook_capability_link(self):
        """
        Verify that webhooks capability link is a full url with a version
        """
        webhook_capability_link = self.webhook['links'].capability
        self.assertTrue(self._has_version(webhook_capability_link))

    def _has_version(self, link):
        """
        check url has version
        @return True if it has version
        """
        return re.search('^/v+\d', urlparse(link).path) is not None
