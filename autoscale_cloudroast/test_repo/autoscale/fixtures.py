"""
:summary: Base Classes for Autoscale Test Suites (Collections of Test Cases)
"""
from cafe.drivers.unittest.fixtures import BaseTestFixture
from autoscale.behaviors import AutoscaleBehaviors
from cloudcafe.common.resources import ResourcePool
from cloudcafe.common.tools.datagen import rand_name
from autoscale.config import AutoscaleConfig
from cloudcafe.auth.config import UserAuthConfig, UserConfig
from autoscale.client import AutoscalingAPIClient, LbaasAPIClient
from cloudcafe.auth.provider import AuthProvider
from cloudcafe.compute.servers_api.client import ServersClient
from autoscale.otter_constants import OtterConstants

import os
import time


class AutoscaleFixture(BaseTestFixture):

    """
    :summary: Fixture for an Autoscale test.
    """

    @classmethod
    def setUpClass(cls):
        """
        Initialize autoscale configs, behaviors and client
        """
        super(AutoscaleFixture, cls).setUpClass()
        cls.resources = ResourcePool()
        cls.autoscale_config = AutoscaleConfig()
        cls.endpoint_config = UserAuthConfig()
        user_config = UserConfig()
        access_data = AuthProvider.get_access_data(cls.endpoint_config,
                                                   user_config)
        server_service = access_data.get_service(
            cls.autoscale_config.server_endpoint_name)
        load_balancer_service = access_data.get_service(
            cls.autoscale_config.load_balancer_endpoint_name)
        server_url = server_service.get_endpoint(
            cls.autoscale_config.region).public_url
        lbaas_url = load_balancer_service.get_endpoint(
            cls.autoscale_config.region).public_url

        cls.tenant_id = cls.autoscale_config.tenant_id

        env = os.environ['OSTNG_CONFIG_FILE']
        if ('preprod' in env.lower()) or ('dev' in env.lower()):
            cls.url = str(cls.autoscale_config.server_endpoint) + '/' + str(cls.tenant_id)
        else:
            autoscale_service = access_data.get_service(
                cls.autoscale_config.autoscale_endpoint_name)
            cls.url = autoscale_service.get_endpoint(
                cls.autoscale_config.region).public_url

        cls.autoscale_client = AutoscalingAPIClient(
            cls.url, access_data.token.id_,
            'json', 'json')
        cls.server_client = ServersClient(
            server_url, access_data.token.id_,
            'json', 'json')
        cls.lbaas_client = LbaasAPIClient(
            lbaas_url, access_data.token.id_,
            'json', 'json')
        cls.autoscale_behaviors = AutoscaleBehaviors(cls.autoscale_config,
                                                     cls.autoscale_client)
        cls.gc_name = cls.autoscale_config.gc_name
        cls.gc_cooldown = int(cls.autoscale_config.gc_cooldown)
        cls.gc_min_entities = int(cls.autoscale_config.gc_min_entities)
        cls.gc_min_entities_alt = int(cls.autoscale_config.gc_min_entities_alt)
        cls.gc_max_entities = int(cls.autoscale_config.gc_max_entities)
        cls.lc_name = cls.autoscale_config.lc_name
        cls.lc_flavor_ref = cls.autoscale_config.lc_flavor_ref
        cls.lc_image_ref = cls.autoscale_config.lc_image_ref
        cls.lc_image_ref_alt = cls.autoscale_config.lc_image_ref_alt
        cls.sp_name = rand_name(cls.autoscale_config.sp_name)
        cls.sp_cooldown = int(cls.autoscale_config.sp_cooldown)
        cls.sp_change = int(cls.autoscale_config.sp_change)
        cls.sp_change_percent = int(cls.autoscale_config.sp_change_percent)
        cls.sp_desired_capacity = int(cls.autoscale_config.sp_desired_capacity)
        cls.sp_policy_type = cls.autoscale_config.sp_policy_type
        cls.upd_sp_change = int(cls.autoscale_config.upd_sp_change)
        cls.lc_load_balancers = cls.autoscale_config.lc_load_balancers
        cls.sp_list = cls.autoscale_config.sp_list
        cls.wb_name = rand_name(cls.autoscale_config.wb_name)
        cls.load_balancer_1 = int(cls.autoscale_config.load_balancer_1)
        cls.load_balancer_2 = int(cls.autoscale_config.load_balancer_2)
        cls.load_balancer_3 = int(cls.autoscale_config.load_balancer_3)
        cls.lb_other_region = int(cls.autoscale_config.lb_other_region)
        cls.interval_time = int(cls.autoscale_config.interval_time)
        cls.timeout = int(cls.autoscale_config.timeout)
        cls.scheduler_interval = OtterConstants.SCHEDULER_INTERVAL
        cls.scheduler_batch = OtterConstants.SCHEDULER_BATCH
        cls.max_maxentities = OtterConstants.MAX_MAXENTITIES
        cls.max_cooldown = OtterConstants.MAX_COOLDOWN
        cls.max_groups = OtterConstants.MAX_GROUPS
        cls.max_policies = OtterConstants.MAX_POLICIES
        cls.max_webhooks = OtterConstants.MAX_WEBHOOKS
        cls.limit_value_all = OtterConstants.LIMIT_VALUE_ALL
        cls.limit_unit_all = OtterConstants.LIMIT_UNIT_ALL
        cls.limit_value_webhook = OtterConstants.LIMIT_VALUE_WEBHOOK
        cls.limit_unit_webhook = OtterConstants.LIMIT_UNIT_WEBHOOK
        cls.non_autoscale_username = cls.autoscale_config.non_autoscale_username
        cls.non_autoscale_password = cls.autoscale_config.non_autoscale_password
        cls.non_autoscale_tenant = cls.autoscale_config.non_autoscale_tenant

    def validate_headers(self, headers):
        """
        Module to validate headers
        """
        self.assertTrue(headers is not None,
                        msg='No headers returned')
        if headers.get('transfer-encoding'):
            self.assertEqual(headers['transfer-encoding'], 'chunked',
                             msg='Response header transfer-encoding is not chunked')
        self.assertTrue(headers['server'] is not None,
                        msg='Response header server is not available')
        self.assertEquals(headers['content-type'], 'application/json',
                          msg='Response header content-type is None')
        self.assertTrue(headers['date'] is not None,
                        msg='Time not included')
        self.assertTrue(headers['x-response-id'] is not None,
                        msg='No x-response-id')

    def empty_scaling_group(self, group, delete=True):
        """
        Given the group, updates the group to be of 0 minentities and maxentities.
        If delete is set to True, the scaling group is deleted.
        """
        servers_on_group = (self.autoscale_client.list_status_entities_sgroups(group.id)).entity
        if servers_on_group.desiredCapacity is not 0:
            self.autoscale_client.update_group_config(
                group_id=group.id,
                name="delete_me_please",
                cooldown=0,
                min_entities=0,
                max_entities=0,
                metadata={})
        if delete:
            self.resources.add(group.id,
                               self.autoscale_client.delete_scaling_group)

    def verify_group_state(self, group_id, desired_capacity):
        """
        Given the group id and the expected desired capacity,
        asserts if the desired capacity is being met by the scaling group
        through the list group status call
        """
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group_id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            desired_capacity,
            msg='Active + Pending servers ({0}) != ({1}) minentities on the group {2}'
            .format((group_state.pendingCapacity + group_state.activeCapacity),
                desired_capacity, group_id))
        self.assertEquals(group_state.desiredCapacity, desired_capacity,
                          msg='Desired capacity ({0}) != ({1}) minentities on the group {2}'
                          .format(group_state.desiredCapacity, desired_capacity, group_id))

    def assert_get_policy(self, created_policy, get_policy, args=False):
        """
        Given the newly created policy dict and the response object from the get
        policy call, asserts all the attributes are equal. args can be at_style,
        cron_style or maas
        """
        self.assertEquals(
            get_policy.id, created_policy['id'],
            msg='Policy Id upon get is not as when created')
        self.assertEquals(
            get_policy.links, created_policy['links'],
            msg='Links for the scaling policy upon get is not as when created')
        self.assertEquals(
            get_policy.name, created_policy['name'],
            msg='Name of the policy upon get is not as when was created')
        self.assertEquals(
            get_policy.cooldown, created_policy['cooldown'],
            msg='Cooldown of the policy upon get != when created')
        if created_policy.get('change'):
            self.assertEquals(
                get_policy.change, created_policy['change'],
                msg='Change in the policy is not as expected')
        elif created_policy.get('change_percent'):
            self.assertEquals(
                get_policy.changePercent, created_policy['change_percent'],
                msg='Change percent in the policy is not as expected')
        elif created_policy.get('desired_capacity'):
            self.assertEquals(
                get_policy.desiredCapacity, created_policy['desired_capacity'],
                msg='Desired capacity in the policy is not as expected')
        else:
            self.fail(msg='Policy does not have a change type')
        if args is 'at_style':
            self.assertEquals(get_policy.args.at, created_policy['schedule_value'],
                              msg='At style schedule policy value not as expected')
        if args is 'cron_style':
            self.assertEquals(get_policy.args.cron, created_policy['schedule_value'],
                              msg='Cron style schedule policy value not as expected')

    def create_default_at_style_policy_wait_for_execution(self, group_id, delay=3,
                                                          change=None,
                                                          scale_down=None):
        """
        Creates an at style scale up/scale down policy to execute at utcnow() + delay and waits
        the scheduler config seconds + delay, so that the policy is picked
        """
        if change is None:
            change = self.sp_change
        if scale_down is True:
            change = -change
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group_id,
            sp_cooldown=0,
            sp_change=change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(delay))
        time.sleep(self.scheduler_interval + delay)

    def get_servers_containing_given_name_on_tenant(self, group_id=None, server_name=None):
        """
        The group_id or the server_name should be provided.
        Given the group id, the server name is got from the group's launch
        config and returns server ID list of servers containing that server name
        on the tenant, from nova.
        list_servers(name=params) returns list of servers that contain the
        specified name within the server name.
        """
        if group_id:
            launch_config = self.autoscale_client.view_launch_config(
                group_id).entity
            params = launch_config.server.name
        elif server_name:
            params = server_name
        list_server_resp = self.server_client.list_servers(name=params)
        filtered_servers = list_server_resp.entity
        return [server.id for server in filtered_servers]

    def wait_for_expected_number_of_active_servers(self, group_id, expected_servers,
                                                   interval_time=None, timeout=None):
        """
        :summary: verify the desired capacity in group state is equal to expected servers
         and waits for the specified number of servers to be active on a group
        :param group_id: Group id
        :param expected_servers: Total active servers expected on the group
        :param interval_time: Time to wait during polling group state
        :param timeout: Time to wait before exiting this function
        :return: returns the list of active servers in the group
        """
        interval_time = interval_time or int(
            self.autoscale_config.interval_time)
        timeout = timeout or int(self.autoscale_config.timeout)
        end_time = time.time() + timeout

        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group_id)
        group_state = group_state_response.entity
        self.assertEquals(group_state.desiredCapacity, expected_servers,
                          msg='Group {0} should have {1} servers, but is trying to '
                          'build {2} servers'.format(group_id, expected_servers,
                                                     group_state.desiredCapacity))
        while time.time() < end_time:
            resp = self.autoscale_client.list_status_entities_sgroups(group_id)
            group_state = resp.entity
            active_list = group_state.active
            self.assertNotEquals((group_state.activeCapacity + group_state.pendingCapacity), 0,
                                 msg='Group Id {0} failed to attempt server creation. Group has no'
                                 ' servers'.format(group_id))
            self.assertEquals(group_state.desiredCapacity, expected_servers,
                              msg='Group {0} should have {1} servers, but has reduced the build {2}'
                              'servers'.format(group_id, expected_servers, group_state.desiredCapacity))
            if len(active_list) == expected_servers:
                return [server.id for server in active_list]
            time.sleep(interval_time)
        else:
            self.fail(
                "wait_for_active_list_in_group_state ran for {0} seconds for group {1} and did not "
                "observe the active server list achieving the expected servers count: {2}.".format(
                    timeout, group_id, expected_servers))

    def check_for_expected_number_of_building_servers(self, group_id, expected_servers,
                                                      desired_capacity=None, server_name=None):
        """
        :summary: verify the desired capacity in group state is equal to expected servers
         and verifies for the specified number of servers with the name specified in the
         group's current launch config, exist on the tenant
        :param group_id: Group id
        :param expected_servers: Total active servers expected on the group
        :param interval_time: Time to wait during polling group state
        :param timeout: Time to wait before exiting this function
        :return: returns the list of active servers in the group
        """
        end_time = time.time() + 120
        desired_capacity = desired_capacity or expected_servers
        while time.time() < end_time:
            group_state = self.autoscale_client.list_status_entities_sgroups(
                group_id).entity
            if group_state.desiredCapacity == desired_capacity:
                if server_name:
                    server_list = self.get_servers_containing_given_name_on_tenant(
                        server_name=server_name)
                else:
                    server_list = self.get_servers_containing_given_name_on_tenant(
                        group_id=group_id)
                if (len(server_list) == expected_servers):
                        return server_list
            time.sleep(5)
        else:
            server_list = self.get_servers_containing_given_name_on_tenant(
                group_id=group_id)
            self.fail(
                'Waited 2 mins for desired capacity/active server list to reach the'
                ' server count of {0}. Has desired capacity {1} on the group {2}'
                ' and {3} servers on the account' .format(desired_capacity,
                group_state.desiredCapacity, group_id, len(server_list)))

    def assert_servers_deleted_successfully(self, server_name, count=0):
        """
        Given a partial server name, polls for 15 mins to assert that the tenant id
        has only specified count of servers containing that name.
        """
        endtime = time.time() + 900
        while time.time() < endtime:
            server_list = self.get_servers_containing_given_name_on_tenant(
                server_name=server_name)
            if len(server_list) == count:
                break
            time.sleep(self.interval_time)
        else:
            self.fail('Servers on the tenant with name {0} were not deleted even'
                      ' after waiting 15 mins'.format(server_name))

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the added resources
        """
        super(AutoscaleFixture, cls).tearDownClass()
        cls.resources.release()


class ScalingGroupFixture(AutoscaleFixture):

    """
    :summary: Creates a scaling group using the default from
              the test data
    """

    @classmethod
    def setUpClass(cls, gc_name=None, gc_cooldown=None, gc_min_entities=None,
                   gc_max_entities=None, gc_metadata=None, lc_name=None,
                   lc_image_ref=None, lc_flavor_ref=None,
                   lc_personality=None, lc_metadata=None,
                   lc_disk_config=None, lc_networks=None,
                   lc_load_balancers=None):
        """
        Creates a scaling group with config values
        """
        super(ScalingGroupFixture, cls).setUpClass()
        if gc_name is None:
            gc_name = rand_name('test_sgroup_fixt_')
        if gc_cooldown is None:
            gc_cooldown = cls.gc_cooldown
        if gc_min_entities is None:
            gc_min_entities = cls.gc_min_entities
        if lc_name is None:
            lc_name = rand_name('test_sg_fixt_srv')
        if lc_flavor_ref is None:
            lc_flavor_ref = cls.lc_flavor_ref
        if lc_image_ref is None:
            lc_image_ref = cls.lc_image_ref
        cls.create_group_response = cls.autoscale_client.\
            create_scaling_group(
                gc_name, gc_cooldown,
                gc_min_entities,
                lc_name, lc_image_ref,
                lc_flavor_ref,
                gc_max_entities=gc_max_entities,
                gc_metadata=gc_metadata,
                lc_personality=lc_personality,
                lc_metadata=lc_metadata,
                lc_disk_config=lc_disk_config,
                lc_networks=lc_networks,
                lc_load_balancers=lc_load_balancers)
        cls.group = cls.create_group_response.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(ScalingGroupFixture, cls).tearDownClass()


class ScalingGroupPolicyFixture(ScalingGroupFixture):

    """
    :summary: Creates a scaling group with policy using the default from
              the test data
    """

    @classmethod
    def setUpClass(cls, name=None, cooldown=None, change=None,
                   change_percent=None, desired_capacity=None,
                   policy_type=None):
        """
        Creates a scaliing policy
        """

        super(ScalingGroupPolicyFixture, cls).setUpClass()
        if name is None:
            name = cls.sp_name
        if cooldown is None:
            cooldown = cls.sp_cooldown
        if policy_type is None:
            policy_type = cls.sp_policy_type
        if change:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name, cooldown=cooldown, change=change, policy_type=policy_type)
        elif change_percent:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name, cooldown=cooldown, change_percent=change_percent,
                policy_type=policy_type)
        elif desired_capacity:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name, cooldown=cooldown, desired_capacity=desired_capacity,
                policy_type=policy_type)
        else:
            change = cls.sp_change
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name, cooldown=cooldown, change=change, policy_type=policy_type)
        cls.create_policy = cls.create_policy_response.entity
        cls.policy = cls.autoscale_behaviors.get_policy_properties(
            cls.create_policy)

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling policy
        """
        super(ScalingGroupPolicyFixture, cls).tearDownClass()


class ScalingGroupWebhookFixture(ScalingGroupPolicyFixture):

    """
    :summary: Creates a scaling group with a scaling policy
              and webhook using the default from the test data
    """

    @classmethod
    def setUpClass(cls, webhook=None, metadata=None):
        """
        Create a webhook
        """
        super(ScalingGroupWebhookFixture, cls).setUpClass()
        if webhook is None:
            webhook = cls.wb_name
        cls.create_webhook_response = cls.autoscale_client.create_webhook(
            group_id=cls.group.id,
            policy_id=cls.policy['id'],
            name=webhook,
            metadata=metadata)
        cls.create_webhook = cls.create_webhook_response.entity
        cls.webhook = cls.autoscale_behaviors.get_webhooks_properties(
            cls.create_webhook)

    @classmethod
    def tearDownClass(cls):
        """
        Delete the webhook
        """
        super(ScalingGroupWebhookFixture, cls).tearDownClass()
