"""
:summary: Base Classes for Autoscale Test Suites (Collections of Test Cases)
"""
from cafe.drivers.unittest.fixtures import BaseTestFixture
from autoscale.behaviors import AutoscaleBehaviors
from cloudcafe.common.resources import ResourcePool
from cloudcafe.compute.common.datagen import rand_name
from autoscale.config import AutoscaleConfig
from cloudcafe.auth.config import UserAuthConfig, UserConfig
from autoscale.client import AutoscalingAPIClient
from cloudcafe.auth.provider import AuthProvider
from cloudcafe.compute.servers_api.client import ServersClient
from autoscale.otter_constants import OtterConstants

import os
from time import sleep


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
        server_url = server_service.get_endpoint(
            cls.autoscale_config.region).public_url

        cls.tenant_id = cls.autoscale_config.tenant_id
        cls.otter_endpoint = cls.autoscale_config.server_endpoint

        env = os.environ['OSTNG_CONFIG_FILE']
        if ('prod.ord' in env.lower()) or ('prod.dfw' in env.lower()):
            autoscale_service = access_data.get_service(
                cls.autoscale_config.autoscale_endpoint_name)
            url = autoscale_service.get_endpoint(
                cls.autoscale_config.region).public_url
        else:
            url = str(cls.otter_endpoint) + '/' + str(cls.tenant_id)

        cls.autoscale_client = AutoscalingAPIClient(
            url, access_data.token.id_,
            'json', 'json')
        cls.server_client = ServersClient(
            server_url, access_data.token.id_,
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
        cls.interval_time = int(cls.autoscale_config.interval_time)
        cls.timeout = int(cls.autoscale_config.timeout)
        cls.scheduler_interval = OtterConstants.SCHEDULER_INTERVAL
        cls.scheduler_batch = OtterConstants.SCHEDULER_BATCH
        cls.max_maxentities = OtterConstants.MAX_MAXENTITIES
        cls.max_cooldown = OtterConstants.MAX_COOLDOWN

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

    def empty_scaling_group(self, group):
        """
        Given the group, updates the group to be of 0 minentities and maxentities.
        """
        self.autoscale_client.update_group_config(
            group_id=group.id,
            name="delete_me_please",
            cooldown=0,
            min_entities=0,
            max_entities=0,
            metadata={})

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
                                                          scale_down=None):
        """
        Creates an at style scale up/scale down policy to execute at utcnow() + delay and waits
        the scheduler config seconds + delay, so that the policy is picked
        """
        if scale_down is True:
            self.sp_change = -self.sp_change
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group_id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(delay))
        sleep(self.scheduler_interval + delay)

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
