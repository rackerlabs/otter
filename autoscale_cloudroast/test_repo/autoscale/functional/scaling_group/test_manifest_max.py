"""
Test to create and verify the listing webhooks.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class GetMaxManifest(ScalingGroupFixture):
    """
    Verify that the webhook manifest is provided when using /groups/[group_id]?webhooks=True
    on a group with the maximum number of policies and the maximum number of webhooks.

    """

    def test_manifest_max(self):
        """
        Create MAX scaling policies, each with MAX webhooks and comfirm that all are
        listed in the manifest.
        """
        # Create and record ids for the maximum number of policies and webhooks
        manifest_dict = {}
        for p in range(0, self.max_policies):
            policy_resp = self.autoscale_behaviors.create_policy_min(self.group.id,
                                                                     sp_name=("policy_{0}".format(p)))
            p_id = policy_resp['id']
            webhook_ids = []
            for w in range(0, self.max_webhooks):
                webhook_resp = self.autoscale_client.create_webhook(self.group.id, p_id,
                                                                    "hook_{0}".format(w))
                hook_obj = webhook_resp.entity[0]
                webhook_ids.append(hook_obj.id)
            manifest_dict[p_id] = sorted(webhook_ids)  # Sort webhooks to verify against rx'd manifest
        # Issues the manifest query, capture resluts, and compare
        list_manifest_resp = \
            self.autoscale_client.view_manifest_config_for_scaling_group(
                self.group.id, webhooks="True")
        list_manifest = list_manifest_resp.entity
        actual_ids = {}
        for policy in list_manifest.scalingPolicies:
            sp_id = policy.id
            rx_webhook_ids = []
            for hook in policy.webhooks:
                rx_webhook_ids.append(hook.id)
            actual_ids[sp_id] = rx_webhook_ids  # Unsorted to verify that the order is correct
        self.assertTrue(manifest_dict == actual_ids,
                        "Recieved manifest did not match expected")
