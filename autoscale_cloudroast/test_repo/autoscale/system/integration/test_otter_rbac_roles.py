"""
System Integration tests for otter's rbac roles
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture
from cafe.drivers.unittest.decorators import tags
from cloudcafe.identity.v2_0.tokens_api.behaviors import \
    TokenAPI_Behaviors as OSTokenAPI_Behaviors
from cloudcafe.identity.v2_0.tokens_api.client import \
    TokenAPI_Client as OSTokenAPI_Client
from cloudcafe.auth.config import UserConfig
from autoscale.client import AutoscalingAPIClient


class OtterRbacTests(ScalingGroupWebhookFixture):

    """
    System tests to verify the rbac roles for otter.
    """
    @classmethod
    def setUpClass(cls):
        """
        Gets password from the config file. All users were created to have the same password.
        """
        super(OtterRbacTests, cls).setUpClass()
        user_config = UserConfig()
        cls.password = user_config.password

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_admin_autoscale_observer(self):
        """
        Given a user with the observer role for Autoscale and admin role for nova
        and lbaas, verify the user has permissions to GET groups, GET a group,
        GET the group state for a group, GET the configs of a group, GET the launch
        configs of a group, LIST policies and GET a policy
        """
        autoscale_na_la_ao = self.autoscale_config.autoscale_na_la_ao
        user_client = self._create_client(autoscale_na_la_ao, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client, 403)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_autoscale_admin(self):
        """
        Given a user with an admin role for Autscale, nova and lbaas, verify the user
        has permissions to perform all CRUD operations in otter.
        """
        autoscale_na_la_aa = self.autoscale_config.autoscale_na_la_aa
        user_client = self._create_client(autoscale_na_la_aa, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_autoscale_observer(self):
        """
        Given a user with observer role for Autoscale, nova and lbaas, ensure the user
        can still perform all the GET operations on Otter.
        """
        autoscale_no_lo_ao = self.autoscale_config.autoscale_no_lo_ao
        user_client = self._create_client(autoscale_no_lo_ao, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client, 403)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_observer_autoscale_admin(self):
        """
        Given a user with an admin role for Autoscale, and observer role for nova and lbaas,
        ensure the user can still perform all admin operations on Otter.
        """
        autoscale_no_lo_aa = self.autoscale_config.autoscale_no_lo_aa
        user_client = self._create_client(autoscale_no_lo_aa, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client)

    @tags(type='rbac', speed='quick')
    def test_nova_admin_lbaas_observer_autoscale_admin(self):
        """
        Given a user with an admin role for Autoscale and Nova, and observer role for lbaas,
        ensure the user can still perform all admin operations on Otter.
        """
        autoscale_na_lo_aa = self.autoscale_config.autoscale_na_lo_aa
        user_client = self._create_client(autoscale_na_lo_aa, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_creator_autoscale_admin(self):
        """
        Given a user with an admin role for Autoscale, and creator role for nova and lbaas,
        ensure the user can still perform all admin operations on Otter.
        """
        autoscale_nc_lc_aa = self.autoscale_config.autoscale_nc_lc_aa
        user_client = self._create_client(autoscale_nc_lc_aa, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_creator_autoscale_observer(self):
        """
        Given a user with an observer role for Autoscale, and creator role for nova and lbaas,
        ensure the user can still perform all observer operations on Otter.
        """
        autoscale_nc_lc_ao = self.autoscale_config.autoscale_nc_lc_ao
        user_client = self._create_client(autoscale_nc_lc_ao, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client, 403)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_no_access_autoscale_admin(self):
        """
        Given a user with an admin role for Autoscale, and no access to nova and lbaas,
        ensure the user can still perform all admin operations on Otter.
        """
        autoscale_nno_lno_aa = self.autoscale_config.autoscale_nno_lno_aa
        user_client = self._create_client(autoscale_nno_lno_aa, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_no_access_autoscale_observer(self):
        """
        Given a user with an observer role for Autoscale, and no access to nova and lbaas,
        ensure the user can still perform all observer operations on Otter.
        """
        autoscale_nno_lno_ao = self.autoscale_config.autoscale_nno_lno_ao
        user_client = self._create_client(autoscale_nno_lno_ao, self.password)
        self._verify_otter_observer_role(user_client)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client, 403)

    @tags(type='rbac', speed='quick')
    def test_nova_lbaas_admin_autoscale_no_access(self):
        """
        Given a user with no access to Autoscale, and admin roles for nova and lbaas,
        ensure the user can not perform any operations on Otter.
        """
        autoscale_na_la_ano = self.autoscale_config.autoscale_na_la_ano
        user_client = self._create_client(autoscale_na_la_ano, self.password)
        self._verify_otter_observer_role(user_client, 403)
        self._verify_otter_admin_roles_other_than_GET_calls(user_client, 403)

    def _create_client(self, username, password):
        """
        Create a client for the given test account
        """
        endpoint = self.endpoint_config.auth_endpoint
        token_client = OSTokenAPI_Client(endpoint, 'json', 'json')
        token_behaviors = OSTokenAPI_Behaviors(token_client)
        access_data = token_behaviors.get_access_data(username,
                                                      password,
                                                      self.tenant_id)
        autoscale_temp_client = AutoscalingAPIClient(url=self.url,
                                                     auth_token=access_data.token.id_,
                                                     serialize_format='json',
                                                     deserialize_format='json')
        return autoscale_temp_client

    def _verify_otter_observer_role(self, user_client, expected_response_code=200):
        """
        verify all the GET calls on a group and policy. Uses the group, policy and webhook
        created as part of the ScalingGroupWebhookFixture imported.
        """
        list_groups_response = user_client.list_scaling_groups()
        self.assertEquals(
            list_groups_response.status_code, expected_response_code,
            msg='List groups returned response code {0}'.format(list_groups_response.status_code))
        get_group_response = user_client.view_manifest_config_for_scaling_group(
            self.group.id)
        self.assertEquals(
            get_group_response.status_code, expected_response_code,
            msg='Get group returned response code {0} on group '
            '{1}'.format(get_group_response.status_code, self.group.id))
        get_group_state_response = user_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(
            get_group_state_response.status_code, expected_response_code,
            msg='Get group state returned response code {0} on group '
            '{1}'.format(get_group_state_response.status_code, self.group.id))
        get_group_config_response = user_client.view_scaling_group_config(
            self.group.id)
        self.assertEquals(
            get_group_config_response.status_code, expected_response_code,
            msg='Get group config returned response code {0} on group '
            '{1}'.format(get_group_config_response.status_code, self.group.id))
        get_launch_config_response = user_client.view_launch_config(
            self.group.id)
        self.assertEquals(
            get_launch_config_response.status_code, expected_response_code,
            msg='Get launch config returned response code {0} on group '
            '{1}'.format(get_launch_config_response.status_code, self.group.id))
        list_policies_response = user_client.list_policies(self.group.id)
        self.assertEquals(
            list_policies_response.status_code, expected_response_code,
            msg='List policies returned response code {0} for the group'
            ' {1}'.format(list_policies_response.status_code, self.group.id))
        get_policy_response = user_client.get_policy_details(
            self.group.id, self.policy['id'])
        self.assertEquals(
            get_policy_response.status_code, expected_response_code,
            msg='Get group returned response code {0} on group '
            '{1}'.format(get_policy_response.status_code, self.group.id))

    def _verify_otter_admin_roles_other_than_GET_calls(self, user_client,
                                                       expected_response_code=None,
                                                       lc_load_balancers=None):
        """
        verify all the otter api calls except for all the GET calls, as
        _verify_otter_observer_role covers them already.
        """
        response_codes = {'create': 201, 'upd-del': 204, 'execute': 202, 'get': 200}
        if expected_response_code:
            response_codes.update(dict.fromkeys(['create', 'upd-del', 'execute', 'get'],
                                                expected_response_code))

        # create group
        create_scaling_group_response = user_client.create_scaling_group(
            gc_name='test-group',
            gc_cooldown=1,
            gc_min_entities=0,
            lc_image_ref=self.lc_image_ref,
            lc_flavor_ref=self.lc_flavor_ref,
            lc_name='test-grp-srv',
            lc_load_balancers=lc_load_balancers)
        self.assertEquals(
            create_scaling_group_response.status_code, response_codes['create'],
            msg='Create group returned response code {0}'.format(
                create_scaling_group_response.status_code))

        # update group config
        update_group_config_response = user_client.update_group_config(
            group_id=self.group.id,
            name='update_name',
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities,
            max_entities=self.group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(
            update_group_config_response.status_code, response_codes['upd-del'],
            msg='Update group config returned response code {0} on group '
            '{1}'.format(update_group_config_response.status_code, self.group.id))

        # update launch config
        update_launch_config_response = user_client.update_launch_config(
            group_id=self.group.id,
            name='update_name',
            image_ref=self.group.launchConfiguration.server.imageRef,
            flavor_ref=self.group.launchConfiguration.server.flavorRef)
        self.assertEquals(
            update_launch_config_response.status_code, response_codes['upd-del'],
            msg='Update launch config returned response code {0} on group '
            '{1}'.format(update_launch_config_response.status_code, self.group.id))

        # create policy
        create_policy_response = user_client.create_policy(group_id=self.group.id,
                                                           name='test-policy',
                                                           cooldown=1,
                                                           change=1,
                                                           policy_type='webhook')
        self.assertEquals(
            create_policy_response.status_code, response_codes['create'],
            msg='Create policy returned response code {0} on group '
            '{1}'.format(create_policy_response.status_code, self.group.id))

        # update_policy
        update_policy_response = user_client.update_policy(group_id=self.group.id,
                                                           policy_id=self.policy['id'],
                                                           name='upd_name',
                                                           cooldown=0,
                                                           change=1,
                                                           policy_type='webhook')
        self.assertEquals(
            update_policy_response.status_code, response_codes['upd-del'],
            msg='Update policy returned response code {0} on group '
            '{1}'.format(update_policy_response.status_code, self.group.id))

        # execute_policy
        execute_policy_response = user_client.execute_policy(self.group.id, self.policy['id'])
        self.assertEquals(
            execute_policy_response.status_code, response_codes['execute'],
            msg='Execute policy returned response code {0} on group '
            '{1}'.format(execute_policy_response.status_code, self.group.id))

        # create_webhook
        create_webhook_response = user_client.create_webhook(self.group.id,
                                                             self.policy['id'],
                                                             'test-wb')
        self.assertEquals(
            create_webhook_response.status_code, response_codes['create'],
            msg='Create webhook returned response code {0} on group '
            '{1}'.format(create_webhook_response.status_code, self.group.id))

        # list webhooks
        list_webhook_response = user_client.list_webhooks(self.group.id, self.policy['id'])
        self.assertEquals(
            list_webhook_response.status_code, response_codes['get'],
            msg='List webhooks returned response code {0} on group '
            '{1}'.format(list_webhook_response.status_code, self.group.id))

        # get webhook
        get_webhook_response = user_client.get_webhook(self.group.id,
                                                       self.policy['id'],
                                                       self.webhook['id'])
        self.assertEquals(
            get_webhook_response.status_code, response_codes['get'],
            msg='List webhooks returned response code {0} on group '
            '{1}'.format(get_webhook_response.status_code, self.group.id))

        # update webhook
        update_webhook_response = user_client.update_webhook(self.group.id,
                                                             self.policy['id'],
                                                             self.webhook['id'],
                                                             name='upd-wb',
                                                             metadata={})
        self.assertEquals(
            update_webhook_response.status_code, response_codes['upd-del'],
            msg='Update webhook returned response code {0} on group '
            '{1}'.format(update_webhook_response.status_code, self.group.id))

        # execute webhook
        execute_webhook_response = user_client.execute_webhook(self.webhook['links'].capability)
        self.assertEquals(
            execute_webhook_response.status_code, 202,
            msg='Execute webhook returned response code {0} on group '
            '{1}'.format(execute_webhook_response.status_code, self.group.id))

        # delete webhook
        delete_webhook_response = user_client.delete_webhook(self.group.id,
                                                             self.policy['id'],
                                                             self.webhook['id'])
        self.assertEquals(
            delete_webhook_response.status_code, response_codes['upd-del'],
            msg='Delete webhook returned response code {0} on group '
            '{1}'.format(delete_webhook_response.status_code, self.group.id))

        # delete policy
        delete_policy_response = user_client.delete_scaling_policy(self.group.id,
                                                                   self.policy['id'])
        self.assertEquals(
            delete_policy_response.status_code, response_codes['upd-del'],
            msg='Delete policy returned response code {0} on group '
            '{1}'.format(delete_policy_response.status_code, self.group.id))

        # delete group
        self.resources.add(self.group.id, self.empty_scaling_group(self.group))
        delete_group_response = user_client.delete_scaling_group(self.group.id)
        self.assertEquals(
            delete_group_response.status_code, response_codes['upd-del'],
            msg='Delete group returned response code {0} on group '
            '{1}'.format(delete_group_response.status_code, self.group.id))
