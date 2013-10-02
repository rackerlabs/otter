"""
System Integration tests autoscaling with repose
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest
from cafe.drivers.unittest.decorators import tags


class AutoscaleReposeTests(AutoscaleFixture):

    """
    System tests to verify repose integration with autoscale
    """

    @tags(type='repose')
    def test_system_repose_rate_limits_without_trailing_slash(self):
        """
        Verify the relative and absolute rate limits set by autoscale in repose, using the limits
        api without a trailing slash, returns reponse code 200 and the relative and
        absolute limits
        """
        limits_response = self.autoscale_client.view_limits()
        self.assertEquals(limits_response.status_code, 200,
                          msg='Limits returned response code {0}'.format(limits_response.status_code))
        limits = limits_response.entity
        self.assertEquals(limits.absolute.maxGroups, self.max_groups)
        self.assertEquals(limits.absolute.maxPoliciesPerGroup, self.max_policies)
        self.assertEquals(limits.absolute.maxWebhooksPerPolicy, self.max_webhooks)
        for each_rate in limits.rate:
            if 'tenantId' in each_rate.uri:
                self.assertTrue('/v1\.0/([0-9]+)/.+' in each_rate.regex,
                                msg='the regex in the tenant rate limit is {0}'.format(each_rate.regex))
                for limits in each_rate.limit:
                    self.assertEquals(limits.unit, self.limit_unit_all,
                                      msg='The limits unit for tenant is {0}'.format(limits.unit))
                    self.assertEquals(limits.value, self.limit_value_all,
                                      msg='The limits value for tenant is {0}'.format(limits.value))
                    self.assertEquals(limits.verb, 'ALL',
                                      msg='The verb for tenant is {0}'.format(limits.verb))
            if 'execute' in each_rate.uri:
                self.assertTrue('/v1\.0/execute/(.*)'in each_rate.regex,
                                msg='the regex in the tenant rate limit is {0}'.format(each_rate.regex))
                for limits in each_rate.limit:
                    self.assertEquals(limits.unit, self.limit_unit_webhook,
                                      msg='The limits unit for tenant is {0}'.format(limits.unit))
                    self.assertEquals(limits.value, self.limit_value_webhook,
                                      msg='The limits value for tenant is {0}'.format(limits.value))
                    self.assertEquals(limits.verb, 'ALL',
                                      msg='The verb for tenant is {0}'.format(limits.verb))

    @unittest.skip('AUTO-530')
    def test_system_repose_rate_limits_with_trailing_slash(self):
        """
        Verify the relative and absolute rate limits set by autoscale in repose, using the limits
        api with a trailing slash, returns reponse code 200 and the relative and
        absolute limits
        """
        limits_response = self.autoscale_client.view_limits(self.url + '/limits/')
        self.assertEquals(limits_response.status_code, 200,
                          msg='Limits returned response code {0}'.format(limits_response.status_code))
        limits = limits_response.entity
        self.assertEquals(limits.absolute.maxGroups, self.max_groups)
        self.assertEquals(limits.absolute.maxPoliciesPerGroup, self.max_policies)
        self.assertEquals(limits.absolute.maxWebhooksPerPolicy, self.max_webhooks)
        for each_rate in limits.rate:
            if 'tenantId' in each_rate.uri:
                self.assertTrue('/v1\.0/([0-9]+)/.+' in each_rate.regex,
                                msg='the regex in the tenant rate limit is {0}'.format(each_rate.regex))
                for limits in each_rate.limit:
                    self.assertEquals(limits.unit, self.limit_unit_all,
                                      msg='The limits unit for tenant is {0}'.format(limits.unit))
                    self.assertEquals(limits.value, self.limit_value_all,
                                      msg='The limits value for tenant is {0}'.format(limits.value))
                    self.assertEquals(limits.verb, 'ALL',
                                      msg='The verb for tenant is {0}'.format(limits.verb))
            if 'execute' in each_rate.uri:
                self.assertTrue('/v1\.0/execute/(.*)'in each_rate.regex,
                                msg='the regex in the tenant rate limit is {0}'.format(each_rate.regex))
                for limits in each_rate.limit:
                    self.assertEquals(limits.unit, self.limit_unit_webhook,
                                      msg='The limits unit for tenant is {0}'.format(limits.unit))
                    self.assertEquals(limits.value, self.limit_value_webhook,
                                      msg='The limits value for tenant is {0}'.format(limits.value))
                    self.assertEquals(limits.verb, 'ALL',
                                      msg='The verb for tenant is {0}'.format(limits.verb))

    @tags(type='repose')
    def test_system_repose_list_groups_on_account_without_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose without a trailing slash,
        returns response code 200
        """
        list_response = self.autoscale_client.list_scaling_groups(self.url + '/groups')
        self.assertEquals(list_response.status_code, 200,
                          msg='List scaling group returned response code '
                          '{0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_list_groups_on_account_with_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose with a trailing slash,
        returns response code 200
        """
        list_response = self.autoscale_client.list_scaling_groups(self.url + '/groups/')
        self.assertEquals(list_response.status_code, 200,
                          msg='List scaling group returned response code'
                          ' {0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_get_non_existant_group_without_trailing_slash(self):
        """
        Verify get scaling groups for an invalid group id through repose without a trailing slash,
        returns response code 404
        """
        list_response = self.autoscale_client.list_scaling_groups(self.url + '/groups/76765')
        self.assertEquals(list_response.status_code, 404,
                          msg='List scaling group returned response code '
                          '{0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_get_non_existant_group_with_trailing_slash(self):
        """
        Verify get scaling groups for an invalid group id through repose with a trailing slash,
        returns response code 404
        """
        list_response = self.autoscale_client.list_scaling_groups(self.url + '/groups/76765/')
        self.assertEquals(list_response.status_code, 404,
                          msg='List scaling group returned response code '
                          '{0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_execute_webhook(self):
        """
        Verify execute webhook through repose returns response code 202
        """
        group = self.autoscale_behaviors.create_scaling_group_min().entity
        policy = self.autoscale_behaviors.create_policy_webhook(group.id, {'change': 1})
        execute_wb_response = self.autoscale_client.execute_webhook(policy['webhook_url'])
        self.assertEquals(execute_wb_response.status_code, 202,
                          msg='List scaling group returned response code '
                          '{0}'.format(execute_wb_response.status_code))
