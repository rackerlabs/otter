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
            cls.url = str(cls.autoscale_config.server_endpoint) + \
                '/' + str(cls.tenant_id)
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
        cls.check_type = cls.autoscale_config.check_type
        cls.check_url = cls.autoscale_config.check_url
        cls.check_method = cls.autoscale_config.check_method
        cls.check_timeout = cls.autoscale_config.check_timeout
        cls.check_period = cls.autoscale_config.check_period
        cls.monitoring_zones = ['mzord', 'mzdfw', 'mziad']
        cls.target_alias = cls.autoscale_config.target_alias
        cls.alarm_criteria = cls.autoscale_config.alarm_criteria
        cls.upd_sp_change = int(cls.autoscale_config.upd_sp_change)
        cls.lc_load_balancers = cls.autoscale_config.lc_load_balancers
        cls.sp_list = cls.autoscale_config.sp_list
        cls.wb_name = rand_name(cls.autoscale_config.wb_name)
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
        cls.pagination_limit = OtterConstants.PAGINATION_LIMIT
        cls.personality_maxlength = OtterConstants.PERSONALITY_MAXLENGTH
        cls.max_personalities = OtterConstants.PERSONALITIES_PER_SERVER
        cls.personality_max_file_size = OtterConstants.PERSONAITY_FILE_SIZE
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
        servers_on_group = (
            self.autoscale_client.list_status_entities_sgroups(group.id)).entity
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
            self.assertEquals(
                get_policy.args.at, created_policy['schedule_value'],
                msg='At style schedule policy value not as expected')
        if args is 'cron_style':
            self.assertEquals(
                get_policy.args.cron, created_policy['schedule_value'],
                msg='Cron style schedule policy value not as expected')

    def assert_group_state(self, group_state):
        """
        Given the group state, verify active, pending and
        desired capacity are as expected
        """
        self.assertEquals(len(group_state.active), group_state.activeCapacity)
        self.assertGreaterEqual(group_state.pendingCapacity, 0)
        self.assertEquals(group_state.desiredCapacity,
                          group_state.activeCapacity + group_state.pendingCapacity)
        self.assertFalse(group_state.paused)

    def create_default_at_style_policy_wait_for_execution(
        self, group_id, delay=3,
            change=None, scale_down=None):
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

    def verify_server_count_using_server_metadata(self, group_id, expected_count):
        """
        Asserts the expected count is the number of servers with the groupid
        in the metadata. Fails if the count is not met in 60 seconds.
        """
        end_time = time.time() + 60
        while time.time() < end_time:
            list_servers_on_tenant = self.server_client.list_servers_with_detail().entity
            metadata_list = [self.autoscale_behaviors.to_data(each_server.metadata) for each_server
                             in list_servers_on_tenant]
            group_ids_list_from_metadata = [each.get('rax:auto_scaling_group_id') for each
                                            in metadata_list]
            actual_count = group_ids_list_from_metadata.count(group_id)
            if actual_count is expected_count:
                break
            time.sleep(5)
        else:
            self.fail('Waited 60 seconds, expecting {0} servers with group id : {1} in the '
                      'metadata but has {2} servers'.format(expected_count, group_id,
                                                            actual_count))

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
            self.assertNotEquals(
                (group_state.activeCapacity + group_state.pendingCapacity), 0,
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

    def wait_for_expected_group_state(self, group_id, expected_servers, wait_time=120):
        """
        :summary: verify the group state reached the expected servers count.
        :param group_id: Group id
        :param expected_servers: Number of servers expected
        """
        end_time = time.time() + wait_time
        while time.time() < end_time:
            group_state = self.autoscale_client.list_status_entities_sgroups(group_id).entity
            if group_state.desiredCapacity == expected_servers:
                return
            time.sleep(self.interval_time)
        else:
            self.fail(
                "wait_for_exepected_group_state ran for 120 seconds for group {0} and did not "
                "observe the active server list achieving the expected servers count: {1}.".format(
                    group_id, expected_servers))

    def check_for_expected_number_of_building_servers(
        self, group_id, expected_servers,
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
                                                          group_state.desiredCapacity, group_id,
                                                          len(server_list)))

    def assert_servers_deleted_successfully(self, server_name, count=0):
        """
        Given a partial server name, polls for 15 mins to assert that the tenant id
        has only specified count of servers containing that name, and returns the list
        of servers.
        """
        endtime = time.time() + 900
        while time.time() < endtime:
            server_list = self.get_servers_containing_given_name_on_tenant(
                server_name=server_name)
            if len(server_list) == count:
                return server_list
            time.sleep(self.interval_time)
        else:
            self.fail('Servers on the tenant with name {0} were not deleted even'
                      ' after waiting 15 mins'.format(server_name))

    def delete_nodes_in_loadbalancer(self, node_id_list, load_balancer):
        """
        Given the node id list and load balancer id, check for lb status
        'PENDING UPDATE' and delete node when lb is ACTIVE
        """
        for each_node_id in node_id_list:
            end_time = time.time() + 120
            while time.time() < end_time:
                delete_response = self.lbaas_client.delete_node(load_balancer, each_node_id)
                if 'PENDING_UPDATE' in delete_response.text:
                    time.sleep(2)
                else:
                    break
            else:
                print 'Tried deleting node for 2 mins but lb {0} remained in PENDING_UPDATE'
                ' state'.format(load_balancer)

    def get_total_num_groups(self):
        """
        Returns the total number of groups on an account.
        """
        list_groups = self.autoscale_client.list_scaling_groups().entity
        group_num = len(list_groups.groups)
        while (hasattr(list_groups.groups_links, 'next')):
            list_groups = self.autoscale_client.list_scaling_groups(
                url=list_groups.groups_links.next).entity
            group_num += len(list_groups.groups)
        return group_num

    def get_total_num_policies(self, group_id):
        """
        Returns the total number of policies on the given scaling group.
        """
        list_policies = self.autoscale_client.list_policies(group_id).entity
        policies_num = len(list_policies.policies)
        while (hasattr(list_policies.policies_links, 'next')):
            list_policies = self.autoscale_client.list_policies(
                url=list_policies.policies_links.next, group_id=group_id).entity
            policies_num += len(list_policies.policies)
        return policies_num

    def get_total_num_webhooks(self, group_id, policy_id):
        """
        Returns the total number of webhooks on a given policy.
        Note: This will work only after the test webhook pagination branch is merged
        """
        list_webhooks = self.autoscale_client.list_webhooks(group_id, policy_id).entity
        webhooks_num = len(list_webhooks.webhooks)
        while (hasattr(list_webhooks.webhooks_links, 'next')):
            list_webhooks = self.autoscale_client.list_webhooks(
                url=list_webhooks.webhooks_links.next).entity
            webhooks_num += len(list_webhooks.webhooks)
        return webhooks_num

    def successfully_delete_given_loadbalancer(self, lb_id):
        """
        Given the load balancer Id, tries to delete the load balancer for 15 minutes,
        until a 204 is received
        """
        endtime = time.time() + 900
        while time.time() < endtime:
            del_lb = self.lbaas_client.delete_load_balancer(lb_id)
            if del_lb.status_code == 202:
                break
            time.sleep(self.interval_time)
        else:
            self.fail('Deleting load balancer failed, as load balncer remained in building'
                      ' after waiting 15 mins'.format(lb_id))

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
                gc_name=gc_name,
                gc_cooldown=gc_cooldown,
                gc_min_entities=gc_min_entities,
                lc_name=lc_name,
                lc_image_ref=lc_image_ref,
                lc_flavor_ref=lc_flavor_ref,
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
