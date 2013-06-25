"""
Test to verify negative cases for webhooks.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture
from autoscale.status_codes import HttpStatusCodes
import urlparse


class ScalingWebhooksNegative(ScalingGroupPolicyFixture):
    """
    Verify negatice scenarios for webhooks
    """

    @classmethod
    def setUpClass(cls):
        """
        Create scaling group with policy.
        """
        super(ScalingWebhooksNegative, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete scaling group.
        """
        super(ScalingWebhooksNegative, cls).tearDownClass()

    def test_webhooks_nonexistant(self):
        """
        Negative Test: Verify no webhooks on a newly created policy.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        policy = self.autoscale_behaviors.create_policy_min(group.id)
        list_webhooks_resp = self.autoscale_client.list_webhooks(
            group.id, policy['id'])
        list_webhooks = list_webhooks_resp.entity
        self.assertEquals(list_webhooks_resp.status_code, 200,
                          msg='List webhooks failed with {0}'
                          .format(list_webhooks_resp.status_code))
        self.validate_headers(list_webhooks_resp.headers)
        self.assertEquals(list_webhooks, [],
                          msg='Unexpected webhooks exist on the scaling policy')

    def test_webhook_name_blank(self):
        """
        Negative Test: Webhooks should not get created with an empty
        name.
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name='')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_webhooks_name_whitespace(self):
        """
        Negative Test: Webhooks should not get created with
        name as whitespace
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name='')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_get_invalid_webhook_id(self):
        """
        Negative Test: Get Webhooks with invalid webhook id should fail with
        resource not found 404
        """
        webhook = 13344
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.get_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            webhook_id=webhook)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_update_invalid_webhook_id(self):
        """
        Negative Test: Update Webhooks with invalid webhook id should fail with
        resource not found 404
        """
        webhook = 13344
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            webhook_id=webhook,
            name=self.wb_name,
            metadata={})
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_get_webhook_after_deletion(self):
        """
        Negative Test: Get webhook when webhook is deleted should fail with
        resource not found 404
        """
        create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_resp.entity)
        del_resp = self.autoscale_client.delete_webhook(group_id=self.group.id,
                                                        policy_id=self.policy[
                                                            'id'],
                                                        webhook_id=webhook['id'])
        self.assertEquals(
            create_resp.status_code, 201, msg='create webhook failed')
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete webhook failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.get_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            webhook_id=webhook['id'])
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_update_webhook_after_deletion(self):
        """
        Negative Test: Update webhook when webhook is deleted should fail with
        resource not found 404
        """
        create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_resp.entity)
        del_resp = self.autoscale_client.delete_webhook(group_id=self.group.id,
                                                        policy_id=self.policy[
                                                            'id'],
                                                        webhook_id=webhook['id'])
        self.assertEquals(
            create_resp.status_code, 201, msg='create webhook failed')
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete webhook failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            webhook_id=webhook[
                'id'],
            name=self.wb_name,
            metadata={})
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create webhooks succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))
        self.assertTrue(create_error is None,
                        msg='Create webhooks with invalid request returned: {0}'
                        .format(create_error))

    def test_execute_invalid_version_webhook(self):
        """
        Negative Test: Execute a webhook with an invalid version.
        """
        create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_resp.entity)
        self.assertEquals(
            create_resp.status_code, 201, msg='create webhook failed')
        cap_url = webhook['links'].capability
        (scheme, netloc, path, _, _, _) = urlparse.urlparse(cap_url)
        segments = path.split('/')
        segments[-3] = '10'
        invalid_cap_url = urlparse.urlunparse((
            scheme,
            netloc,
            '/'.join(segments),
            '', '', ''))

        execute_wb_resp = self.autoscale_client.execute_webhook(
            invalid_cap_url)
        self.assertEquals(execute_wb_resp.status_code, 202,
                          msg='Execute webhook did not fail. Response: {0}'
                          .format(execute_wb_resp.status_code))

    def test_execute_nonexistant_webhook(self):
        """
        Negative Test: Execute a invalid webhook.
        """
        create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_resp.entity)
        self.assertEquals(
            create_resp.status_code, 201, msg='create webhook failed')
        cap_url = webhook['links'].capability
        (scheme, netloc, path, _, _, _) = urlparse.urlparse(cap_url)
        segments = path.split('/')
        segments[-2] = 'INVALID'
        invalid_cap_url = urlparse.urlunparse((
            scheme,
            netloc,
            '/'.join(segments),
            '', '', ''))

        execute_wb_resp = self.autoscale_client.execute_webhook(
            invalid_cap_url)
        self.assertEquals(execute_wb_resp.status_code, 202,
                          msg='Execute webhook did not fail. Response: {0}'
                              .format(execute_wb_resp.status_code))

    def test_execute_webhook_after_deletion(self):
        """
        Negative Test: Execute a webhook after it has been deleted.
        """
        create_resp = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=self.policy[
                'id'],
            name=self.wb_name)
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            create_resp.entity)
        cap_url = webhook['links'].capability
        del_resp = self.autoscale_client.delete_webhook(group_id=self.group.id,
                                                        policy_id=self.policy[
                                                            'id'],
                                                        webhook_id=webhook['id'])
        self.assertEquals(
            create_resp.status_code, 201, msg='create webhook failed')
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete webhook failed')
        execute_wb_resp = self.autoscale_client.execute_webhook(cap_url)
        self.assertEquals(execute_wb_resp.status_code, 202,
                          msg='Execute webhook failed with {0}'
                          .format(execute_wb_resp.status_code))
