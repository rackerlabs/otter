"""
System Integration tests autoscaling with repose
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.identity.v2_0.tokens_api.behaviors import \
    TokenAPI_Behaviors as OSTokenAPI_Behaviors
from cloudcafe.identity.v2_0.tokens_api.client import \
    TokenAPI_Client as OSTokenAPI_Client
from autoscale.client import AutoscalingAPIClient
from cafe.drivers.unittest.decorators import tags


class AutoscaleReposeUnauthTests(AutoscaleFixture):

    """
    System tests to verify repose integration with autoscale
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a client for a test account that does not have the autoscale endpoint
        in its service catalog
        """
        super(AutoscaleReposeUnauthTests, cls).setUpClass()
        cls.url = cls.url.replace(cls.tenant_id, cls.non_autoscale_tenant)
        endpoint = cls.endpoint_config.auth_endpoint
        token_client = OSTokenAPI_Client(
            endpoint, 'json', 'json')
        token_behaviors = OSTokenAPI_Behaviors(token_client)
        access_data = token_behaviors.get_access_data(cls.non_autoscale_username,
                                                      cls.non_autoscale_password,
                                                      cls.non_autoscale_tenant)
        cls.autoscale_temp_client = AutoscalingAPIClient(
            url=cls.url, auth_token=access_data.token.id_, serialize_format='json',
            deserialize_format='json')

    @tags(type='repose')
    def test_system_repose_unauthenticated_rate_limits_without_trailing_slash(self):
        """
        Verify the relative rate limit api without a trailing slash, when unauthenticated,
        returns reponse code 403
        """
        limits_response = self.autoscale_temp_client.view_limits()
        self.assertEquals(limits_response.status_code, 403,
                          msg='Get Limits returned response code {0}'.format(
                          limits_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthenticated_rate_limits_with_trailing_slash(self):
        """
        Verify the relative rate limit api with a trailing slash, when unauthenticated,
        returns reponse code 403
        """
        limits_response = self.autoscale_temp_client.view_limits(self.url + '/limits/')
        self.assertEquals(limits_response.status_code, 403,
                          msg='Limits returned response code {0}'.format(
                          limits_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthenticated_list_groups_on_account_without_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose without a trailing slash,
        when unauthenticated, returns response code 403
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups')
        self.assertEquals(list_response.status_code, 403,
                          msg='List scaling group returned response code {0}'.format(
                          list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthenticated_list_groups_on_account_with_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose with a trailing slash,
        when unauthenticated, returns response code 403
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups/')
        self.assertEquals(list_response.status_code, 403,
                          msg='List scaling group returned response code {0}'.format(
                          list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthenticated_list_groups_on_account_with_non_existant_group(self):
        """
        Verify GET non existing scaling groups through repose without a trailing slash,
        when unauthenticated, returns response code 403
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups/76765')
        self.assertEquals(list_response.status_code, 403,
                          msg='List scaling group returned response code {0}'.format(
                          list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthenticated_execute_webhook(self):
        """
        Verify execute webhook of a tenant by another tenant returns response code 202
        """
        group = self.autoscale_behaviors.create_scaling_group_min().entity
        policy = self.autoscale_behaviors.create_policy_webhook(group.id, {'change': 1})
        execute_wb_response = self.autoscale_temp_client.execute_webhook(policy['webhook_url'])
        self.assertEquals(execute_wb_response.status_code, 202,
                          msg='List scaling group returned response code {0}'.format(
                          execute_wb_response.status_code))
