"""
@summary: Base Classes for Autoscale Test Suites (Collections of Test Cases)
@note: Correspondes DIRECTLY TO A unittest.TestCase
@see: http://docs.python.org/library/unittest.html#unittest.TestCase
@copyright: Copyright (c) 2012 Rackspace US, Inc.
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

import os


class AutoscaleFixture(BaseTestFixture):

    """
    @summary: Fixture for an Autoscale test.
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

        autoscale_service = access_data.get_service(
            cls.autoscale_config.autoscale_endpoint_name)

        server_service = access_data.get_service(
            cls.autoscale_config.server_endpoint_name)
        server_url = server_service.get_endpoint(
            cls.autoscale_config.region).public_url

        cls.tenant_id = cls.autoscale_config.tenant_id
        env = os.environ['OSTNG_CONFIG_FILE']
        if 'dev' in env.lower():
            url = 'http://localhost:9000/v1.0/{0}'.format(cls.tenant_id)
        elif 'prod' in env.lower():
            url = 'https://autoscale.api.rackspacecloud.com/v1.0/{0}'.format(
                cls.tenant_id)
        else:
            url = autoscale_service.get_endpoint(
                cls.autoscale_config.region).public_url

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

    def validate_headers(self, headers):
        """
        Module to validate headers
        """
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

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the added resources
        """
        super(AutoscaleFixture, cls).tearDownClass()
        cls.resources.release()


class ScalingGroupFixture(AutoscaleFixture):

    """
    @summary: Creates a scaling group using the default from
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
    @summary: Creates a scaling group with policy using
    the default from the test data
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
    @summary: Creates a scaling group with a scaling policy
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
