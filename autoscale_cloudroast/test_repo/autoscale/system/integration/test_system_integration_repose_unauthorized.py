"""
System Integration tests autoscaling with repose when unauthorized
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from autoscale.client import AutoscalingAPIClient
from cafe.drivers.unittest.decorators import tags


class AutoscaleReposeUnauthTests(AutoscaleFixture):

    """
    System tests to verify repose integration with autoscale when unauthorized
    """

    @classmethod
    def setUpClass(cls):
        """
        Create an autoscale api client for requests, without authorization
        """
        super(AutoscaleReposeUnauthTests, cls).setUpClass()
        cls.autoscale_temp_client = AutoscalingAPIClient(
            url=cls.url, auth_token=None, serialize_format='json',
            deserialize_format='json')

    @tags(type='repose')
    def test_system_repose_unauthorized_rate_limits_without_trailing_slash(self):
        """
        Verify the relative rate limit api without a trailing slash, when unauthorized,
        returns reponse code 401
        """
        limits_response = self.autoscale_temp_client.view_limits()
        self.assertEquals(limits_response.status_code, 401,
            msg='Get Limits returned response code {0}'.format(limits_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthorized_rate_limits_with_trailing_slash(self):
        """
        Verify the relative rate limit api with a trailing slash, when unauthorized,
        returns reponse code 401
        """
        limits_response = self.autoscale_temp_client.view_limits(self.url + '/limits/')
        self.assertEquals(limits_response.status_code, 401,
            msg='Limits returned response code {0}'.format(limits_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthorized_list_groups_on_account_without_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose without a trailing slash,
        when unauthorized, returns response code 401
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups')
        self.assertEquals(list_response.status_code, 401,
            msg='List scaling group returned response code {0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthorized_list_groups_on_account_with_trailing_slash(self):
        """
        Verify list scaling groups for a tenant through repose with a trailing slash,
        when unauthorized, returns response code 401
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups/')
        self.assertEquals(list_response.status_code, 401,
            msg='List scaling group returned response code {0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthorized_list_groups_on_account_with_non_existant_group(self):
        """
        Verify GET non existing scaling groups through repose without a trailing slash,
        when unauthorized, returns response code 401
        """
        list_response = self.autoscale_temp_client.list_scaling_groups(self.url + '/groups/76765')
        self.assertEquals(list_response.status_code, 401,
            msg='List scaling group returned response code {0}'.format(list_response.status_code))

    @tags(type='repose')
    def test_system_repose_unauthorized_execute_webhook(self):
        """
        Verify execute webhook through repose returns response code 202,
        even when unauthorized
        """
        group = self.autoscale_behaviors.create_scaling_group_min().entity
        policy = self.autoscale_behaviors.create_policy_webhook(group.id, {'change': 1})
        execute_wb_response = self.autoscale_temp_client.execute_webhook(policy['webhook_url'])
        self.assertEquals(execute_wb_response.status_code, 202,
            msg='List scaling group returned response code {0}'.format(
                execute_wb_response.status_code))
