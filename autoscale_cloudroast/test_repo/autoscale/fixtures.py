"""
:summary: Base Classes for Autoscale Test Suites (Collections of Test Cases)
"""
from __future__ import print_function


import json
import time
from functools import partial
from unittest import skip

from autoscale_fixtures.behaviors import AutoscaleBehaviors
from autoscale_fixtures.client import (
    AutoscalingAPIClient, LbaasAPIClient, RackConnectV3APIClient
)
from autoscale_fixtures.config import AutoscaleConfig
from autoscale_fixtures.otter_constants import OtterConstants

from cafe.drivers.unittest.fixtures import BaseTestFixture

from cloudcafe.auth.config import UserAuthConfig, UserConfig
from cloudcafe.auth.provider import AuthProvider

from cloudcafe.common.resources import ResourcePool
from cloudcafe.common.tools.datagen import rand_name
from cloudcafe.compute.images_api.client import ImagesClient
from cloudcafe.compute.servers_api.client import ServersClient


def _make_client(access_data, service_name, region, client_cls, debug_name):
    """
    Create a client using the `client_cls`, assuming it takes a url, an
    auth token, serialize format, and deserialize format.

    Extacts the URL and token from the access_data.

    The autoscale client is special in that it extracts the URL from the
    config, in some cases.
    """
    url = None

    # If not production or staging, always use the configured server
    # endpoint for autoscale instead of what's in the service catalog.
    if (service_name == "autoscale" and
            autoscale_config.environment not in ('production', 'staging')):
        url = "{0}/{1}".format(
            autoscale_config.server_endpoint, autoscale_config.tenant_id)
        print(" ------ Using non-production, non-staging otter --------")

    else:
        service = access_data.get_service(service_name)
        if service is not None:
            url = service.get_endpoint(region).public_url

    if url is not None:
        return client_cls(url, access_data.token.id_, 'json', 'json')
    else:
        print("This account does not support {0}.".format(debug_name))
        return None


def _set_up_clients():
    """
    Read the user creds from the configuration file in and constructs all the
    service clients.  If it can't authenticate, or it cannot construct the
    autoscale/server/lbaas clients, then it fails.

    The RCv3 client is not created if the account does not have access to RCv3
    or if RCv3 configuration parameters are not present or invalid.
    """
    user_config = UserConfig()
    access_data = AuthProvider.get_access_data(endpoint_config, user_config)

    if access_data is None:
        raise Exception(
            "Unable to authenticate against identity to get auth token and "
            "service catalog.")

    _autoscale_client = _make_client(
        access_data,
        autoscale_config.autoscale_endpoint_name,
        autoscale_config.region,
        AutoscalingAPIClient,
        "Autoscale")

    _server_client = _make_client(
        access_data,
        autoscale_config.server_endpoint_name,
        autoscale_config.server_region_override or autoscale_config.region,
        ServersClient,
        "Nova Compute")

    _images_client = _make_client(
        access_data,
        autoscale_config.server_endpoint_name,
        autoscale_config.region,
        ImagesClient,
        "Nova images")

    _lbaas_client = _make_client(
        access_data,
        autoscale_config.load_balancer_endpoint_name,
        autoscale_config.lbaas_region_override or autoscale_config.region,
        LbaasAPIClient,
        "Cloud Load Balancers")

    _rcv3_client = None
    if _rcv3_cloud_network and _rcv3_load_balancer_pool:
        _rcv3_client = _make_client(
            access_data,
            autoscale_config.rcv3_endpoint_name,
            autoscale_config.rcv3_region_override or autoscale_config.region,
            RackConnectV3APIClient,
            "RackConnect v3")
    else:
        print("Not enough test configuration for RCv3 provided. "
              "Will not run RCv3 tests.")

    if not all([x is not None for x in (_autoscale_client, _server_client,
                                        _lbaas_client)]):
        raise Exception(
            "Unable to instantiate all necessary clients.")

    return (_autoscale_client, _server_client, _images_client, _lbaas_client,
            _rcv3_client)


# Global testing state - unfortunate, but only needs to be done once and also
# makes it easier to skip tests based on configs and clients.

autoscale_config = AutoscaleConfig()
endpoint_config = UserAuthConfig()

# Get optional RCV3 values.  These might not be present in the config
# file.
try:
    _rcv3_load_balancer_pool = json.loads(
        autoscale_config.rcv3_load_balancer_pool)
except Exception:
    _rcv3_load_balancer_pool = None

_rcv3_cloud_network = autoscale_config.rcv3_cloud_network

(autoscale_client, server_client, images_client,
 lbaas_client, rcv3_client) = _set_up_clients()


def image_ids_with_and_without_name(images_client, name="Ubuntu"):
    """
    Fetch image IDs, from Nova that can be used as imageRef in tests
    Note: Serves the same purpose as integration.lib.nova.fetch_ubuntu_image_id
    in trial integration tests
    """
    images = images_client.list_images().entity
    base, other = None, None
    for image in images:
        if name in image.name:
            base = image.id
        else:
            other = image.id
    if base is None:
        raise Exception("Couldn't get {} image".format(name))
    return base, other


def only_run_if_mimic_is(should_mimic_be_available):
    """
    Decorator that only runs a test if mimic is equal to the given boolean
    ``should_mimic_be_available``.  Otherwise the test is skipped.
    """
    def actual_decorator(f):
        if autoscale_config.mimic != should_mimic_be_available:
            msg = "Skipping because mimic is {0}".format(
                "available" if autoscale_config.mimic else "not available")
            return skip(msg)(f)
        return f
    return actual_decorator


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
        cls.autoscale_config = autoscale_config
        cls.endpoint_config = endpoint_config

        cls.tenant_id = cls.autoscale_config.tenant_id

        cls.gc_name = cls.autoscale_config.gc_name
        cls.gc_cooldown = int(cls.autoscale_config.gc_cooldown)
        cls.gc_min_entities = int(cls.autoscale_config.gc_min_entities)
        cls.gc_min_entities_alt = int(cls.autoscale_config.gc_min_entities_alt)
        cls.gc_max_entities = int(cls.autoscale_config.gc_max_entities)
        cls.lc_name = cls.autoscale_config.lc_name
        cls.lc_flavor_ref = cls.autoscale_config.lc_flavor_ref
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
        cls.cron_wait_timeout = 60 + cls.scheduler_interval + 5
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
        cls.non_autoscale_username = (
            cls.autoscale_config.non_autoscale_username)
        cls.non_autoscale_password = (
            cls.autoscale_config.non_autoscale_password)
        cls.non_autoscale_tenant = cls.autoscale_config.non_autoscale_tenant

        cls.autoscale_client = autoscale_client
        cls.server_client = server_client
        cls.lbaas_client = lbaas_client
        cls.rcv3_client = rcv3_client

        # ImageRefs of ununtu and non-ubuntu images that will be used
        # when creating groups
        image_refs = image_ids_with_and_without_name(images_client)
        cls.lc_image_ref, cls.lc_image_ref_alt = image_refs
        # Unfortunately some of the tests use imageRef from config instead of
        # this class. So, storing the same in config too
        autoscale_config.lc_image_ref = cls.lc_image_ref
        autoscale_config.lc_image_ref_alt = cls.lc_image_ref_alt

        cls.rcv3_load_balancer_pool = _rcv3_load_balancer_pool
        cls.rcv3_cloud_network = _rcv3_cloud_network

        cls.url = autoscale_client.url

        cls.autoscale_behaviors = AutoscaleBehaviors(
            autoscale_config, autoscale_client,
            rcv3_client=rcv3_client
        )

    def validate_headers(self, headers):
        """
        Module to validate headers
        """
        self.assertTrue(headers is not None,
                        msg='No headers returned')
        if headers.get('transfer-encoding'):
            self.assertEqual(
                headers['transfer-encoding'],
                'chunked',
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
            self.autoscale_client.list_status_entities_sgroups(
                group.id)).entity
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
        group_state_response = (
            self.autoscale_client.list_status_entities_sgroups(group_id)
        )
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            desired_capacity,
            msg=('Active + Pending servers ({0}) != ({1}) '
                 'minentities on the group {2}')
            .format((group_state.pendingCapacity + group_state.activeCapacity),
                    desired_capacity, group_id))
        self.assertEquals(group_state.desiredCapacity, desired_capacity,
                          msg='Desired capacity ({0}) != ({1}) '
                          'minentities on the group {2}'
                          .format(group_state.desiredCapacity,
                                  desired_capacity, group_id))

    def assert_get_policy(self, created_policy, get_policy, args=False):
        """
        Given the newly created policy dict and the response object from the
        get policy call, asserts all the attributes are equal. args can be
        at_style or  cron_style
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
        self.assertEquals(
            group_state.desiredCapacity,
            group_state.activeCapacity + group_state.pendingCapacity)
        self.assertFalse(group_state.paused)

    def create_default_at_style_policy_wait_for_execution(
        self, group_id, delay=3,
            change=None, scale_down=None):
        """
        Creates an at style scale up/scale down policy to execute at
        utcnow() + delay and waits the scheduler config seconds +
        delay, so that the policy is picked
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

    def get_non_deleting_servers(self, name=None):
        """
        Get servers that are not in the process of getting deleted

        :param name: if given, return servers with this name
        """
        return filter(
            lambda s: s.task_state != 'deleting' and s.status != 'DELETED',
            self.server_client.list_servers_with_detail(
                name=name).entity)

    def get_servers_containing_given_name_on_tenant(
            self, group_id=None, server_name=None):
        """
        Get a list of server IDs not marked pending deletion from Nova
        based on the given server_name. If the group_id is given, use
        the server_name extracted from the launch config instead
        """
        if group_id:
            launch_config = self.autoscale_client.view_launch_config(
                group_id).entity
            params = launch_config.server.name
        elif server_name:
            params = server_name
        return [server.id for server in self.get_non_deleting_servers(params)]

    def get_group_servers_based_on_metadata(self, group_id):
        """
        Returns a list of servers that belong to a group, from looking at the
        server metadata
        """
        def is_in_group(server):
            metadata = self.autoscale_behaviors.to_data(server.metadata)
            return metadata.get('rax:auto_scaling_group_id') == group_id

        return [s for s in self.get_non_deleting_servers() if is_in_group(s)]

    def verify_server_count_using_server_metadata(self, group_id,
                                                  expected_count,
                                                  time_scale=True):
        """
        Asserts the expected count is the number of servers with the groupid
        in the metadata. Fails if the count is not met in 60 seconds.
        """
        def verify(elapsed_time):
            actual_count = len(
                self.get_group_servers_based_on_metadata(group_id)
            )
            if actual_count != expected_count:
                self.fail(
                    'Waited {0} seconds, expecting {1} servers with group id '
                    ': {1} in the metadata but has {2} servers'.format(
                        elapsed_time, expected_count, group_id, actual_count))

        return self.autoscale_behaviors.retry(
            verify, timeout=60, interval_time=5, time_scale=time_scale)

    def wait_for_expected_number_of_active_servers(self, group_id,
                                                   expected_servers,
                                                   interval_time=None,
                                                   timeout=None,
                                                   api="Autoscale",
                                                   time_scale=True):
        """This thunks to its replacement in Behaviors.
        Please refer to Autoscale's behaviors.py for more details.
        """
        return (self.autoscale_behaviors
                .wait_for_expected_number_of_active_servers(
                    group_id, expected_servers, interval_time, timeout,
                    api=api, asserter=self, time_scale=time_scale))

    def wait_for_expected_group_state(self, group_id, expected_servers,
                                      wait_time=180, interval=None,
                                      time_scale=True):
        """
        :summary: verify the group state reached the expected servers count.
        :param group_id: Group id
        :param expected_servers: Number of servers expected
        """
        def check_state(elapsed_time):
            group_state = self.autoscale_client.list_status_entities_sgroups(
                group_id).entity
            if group_state.desiredCapacity != expected_servers:
                self.fail(
                    "wait_for_exepected_group_state ran for {0} seconds for "
                    "group {1} and did not observe the active server list "
                    "achieving the expected servers count: {2}.  "
                    "Got {3} instead.".format(
                        elapsed_time, group_id, expected_servers,
                        group_state.desiredCapacity))
        return self.autoscale_behaviors.retry(
            check_state, timeout=wait_time, interval_time=interval,
            time_scale=time_scale)

    def check_for_expected_number_of_building_servers(
        self, group_id, expected_servers,
            desired_capacity=None, server_name=None, time_scale=True):
        """
        :summary: verify the desired capacity in group state is equal to
            expected servers and verifies for the specified number of servers
            with the name specified in the
         group's current launch config, exist on the tenant
        :param group_id: Group id
        :param expected_servers: Total active servers expected on the group
        :return: returns the list of active servers in the group
        """
        desired_capacity = desired_capacity or expected_servers

        def get_server_list():
            if server_name:
                return self.get_servers_containing_given_name_on_tenant(
                    server_name=server_name)
            else:
                return self.get_servers_containing_given_name_on_tenant(
                    group_id=group_id)

        def check_servers(elapsed_time):
            group_state = self.autoscale_client.list_status_entities_sgroups(
                group_id).entity
            if group_state.desiredCapacity == desired_capacity:
                server_list = get_server_list()
                if (len(server_list) == expected_servers):
                    return server_list

            self.fail(
                'Waited {0} secs for desired capacity/active server list to '
                'reach the server count of {1}. Has desired capacity {2} on '
                'the group {3} and {4} servers on the account. '
                'Filtering by server_name={server_name}'.format(
                    elapsed_time,
                    desired_capacity,
                    group_state.desiredCapacity, group_id,
                    len(server_list),
                    server_name=server_name))

        return self.autoscale_behaviors.retry(
            check_servers, timeout=120, interval_time=5, time_scale=time_scale)

    def assert_servers_deleted_successfully(self, server_name, count=0,
                                            time_scale=True):
        """
        Given a partial server name, polls for 15 mins to assert that the
        tenant id has only specified count of servers containing that name,
        and returns the list of servers.
        """
        def check_deleted(elapsed_time):
            server_list = self.get_servers_containing_given_name_on_tenant(
                server_name=server_name)
            if len(server_list) == count:
                return server_list
            self.fail('Servers on the tenant with name {0} were not deleted '
                      'even after waiting {1} seconds'.format(
                          server_name, elapsed_time))
        return self.autoscale_behaviors.retry(
            check_deleted,  timeout=900, time_scale=time_scale)

    def delete_nodes_in_loadbalancer(self, node_id_list, load_balancer):
        """
        Given the node id list and load balancer id, check for lb status
        'PENDING UPDATE' and try to delete all the nodes when lb is ACTIVE.
        """
        for each_node_id in node_id_list:
            def check_deleted(elapsed_time):
                delete_response = self.lbaas_client.delete_node(
                    load_balancer,
                    each_node_id)
                if 'PENDING_UPDATE' in delete_response.text:
                    self.fail(
                      'Tried deleting node for {0} secs but lb {1} remained '
                      'in PENDING_UPDATE state'.format(
                          elapsed_time, load_balancer))
            try:
                self.autoscale_behaviors.retry(
                    check_deleted, timeout=120, interval_time=2)
            except AssertionError as e:
                print(e.message)

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
                url=list_policies.policies_links.next,
                group_id=group_id).entity
            policies_num += len(list_policies.policies)
        return policies_num

    def get_total_num_webhooks(self, group_id, policy_id):
        """
        Returns the total number of webhooks on a given policy.
        """
        list_webhooks = self.autoscale_client.list_webhooks(
            group_id,
            policy_id).entity
        webhooks_num = len(list_webhooks.webhooks)
        while (hasattr(list_webhooks.webhooks_links, 'next')):
            list_webhooks = self.autoscale_client.list_webhooks(
                url=list_webhooks.webhooks_links.next).entity
            webhooks_num += len(list_webhooks.webhooks)
        return webhooks_num

    def successfully_delete_given_loadbalancer(self, lb_id):
        """
        Given the load balancer id, tries to delete the load balancer for 15
        minutes, until a 204 is received.
        """
        def del_lb(elapsed_time):
            del_lb = self.lbaas_client.delete_load_balancer(lb_id)
            if del_lb.status_code != 202:
                self.fail(
                    'Deleting load balancer failed, as load balancer {0} '
                    'remained in building after waiting {1} seconds'.format(
                        lb_id, elapsed_time))
        return self.autoscale_behaviors.retry(del_lb, timeout=900)

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
                   lc_block_device_mapping=None,
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
                lc_block_device_mapping=lc_block_device_mapping,
                lc_load_balancers=lc_load_balancers)
        cls.group = cls.create_group_response.entity
        cls.resources.add(cls.group.id,
                          partial(cls.autoscale_client.delete_scaling_group,
                                  force='true'))

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
                   policy_type=None, **kwargs):
        """
        Creates a scaliing policy
        """

        super(ScalingGroupPolicyFixture, cls).setUpClass(**kwargs)
        if name is None:
            name = cls.sp_name
        if cooldown is None:
            cooldown = cls.sp_cooldown
        if policy_type is None:
            policy_type = cls.sp_policy_type
        if change:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name,
                cooldown=cooldown,
                change=change,
                policy_type=policy_type)
        elif change_percent:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name,
                cooldown=cooldown,
                change_percent=change_percent,
                policy_type=policy_type)
        elif desired_capacity:
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name,
                cooldown=cooldown,
                desired_capacity=desired_capacity,
                policy_type=policy_type)
        else:
            change = cls.sp_change
            cls.create_policy_response = cls.autoscale_client.create_policy(
                group_id=cls.group.id,
                name=name,
                cooldown=cooldown,
                change=change,
                policy_type=policy_type)
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
        Create a webhook.
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
        Delete the webhook.
        """
        super(ScalingGroupWebhookFixture, cls).tearDownClass()
