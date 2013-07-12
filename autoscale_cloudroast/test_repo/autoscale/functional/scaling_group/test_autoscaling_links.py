"""
Test to verify the links on the autoscaling api responses.
"""
import re
import os
from urlparse import urlparse
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class AutoscalingLinksTest(ScalingGroupWebhookFixture):

    """
    Verify links on the autoscaling api response calls
    """
    # Issue AUTO-209 - no bookmark link

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with webhook
        """
        super(AutoscalingLinksTest, cls).setUpClass()
        if 'dev' in os.environ['OSTNG_CONFIG_FILE']:
            cls.url = 'http://127.0.0.1:9000/v1.0'
        if 'preprod' in os.environ['OSTNG_CONFIG_FILE']:
            cls.url = 'http://api0.preprod.ord.as.rax.io:9000/v1.0'

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
        self._validate_links(self.group.links.self, self.group.id)
        get_group_resp = self.autoscale_client.\
            view_manifest_config_for_scaling_group(self.group.links.self)
        self.assertEqual(self.group.id, get_group_resp.entity.id)

    def test_scaling_policy_links(self):
        """
        Verify that scaling policy has links for self
        """
        self.assertTrue(self.policy['links'] is not None,
                        msg='No links returned upon scaling policy creation')
        self._validate_links(self.policy['links'].self, self.policy['id'])
        get_policy_resp = self.autoscale_client.get_policy_details(
            self.group.id, self.policy['links'].self)
        self.assertEqual(self.policy['id'], (get_policy_resp.entity).id)

    def test_webhook_links(self):
        """
        Verify that webhook has links for self
        """
        self.assertTrue(self.webhook['links'] is not None,
                        msg='No links returned upon webhook creation')
        self._validate_links(self.webhook['links'].self, self.webhook['id'])
        get_webhook_resp = self.autoscale_client.get_webhook(
            self.group.id, self.policy['id'], self.webhook['links'].self)
        self.assertEqual(self.webhook['id'], (get_webhook_resp.entity).id)

    def test_webhook_capability_link(self):
        """
        Verify that webhooks capability link is a full url with a version
        """
        self._validate_links(self.webhook['links'].capability)

    def _has_version(self, link):
        """
        check url has version
        @return True if it has version
        """
        return re.search('^/v+\d', urlparse(link).path) is not None

    def _validate_links(self, self_link, item_id=None):
        """
        """
        if item_id:
            self.assertTrue(item_id in self_link,
                            msg='The ID does not exist in self links')
        self.assertTrue(self.url in self_link,
                        msg='The url used to create the group doesnt match'
                        ' the url in self link')
        self.assertTrue(self._has_version(self_link))
