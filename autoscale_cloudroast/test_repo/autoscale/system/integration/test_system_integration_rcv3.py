"""
System Integration tests for autoscaling with RackConnect V3 load balancers
"""
import random
import time

from test_repo.autoscale.fixtures import AutoscaleFixture, safe_hasattr
from cafe.drivers.unittest.decorators import tags
from cloudcafe.common.tools.datagen import rand_name

import common

import unittest


class AutoscaleRackConnectFixture(AutoscaleFixture):
    """
    System tests to verify lbaas integration with autoscale
    """
    @classmethod
    def tearDownClass(cls):
        """
        Class-level teardown.  This releases all the resources acquired by
        the setUpClass method.
        """
        cls.resources.release()

    @classmethod
    def setUpClass(cls):
        """
        Capture the initial state of the shared load balancer pools.
        Since CloudCafe/unittest invokes this method exactly once
        for all tests, the time spent by this method amortizes nicely
        across all tests which can benefit from it.
        """
        super(AutoscaleRackConnectFixture, cls).setUpClass()

        cls.common = common.CommonTestUtilities(cls.server_client,
                                                cls.autoscale_client,
                                                cls.lbaas_client)

        cls.cloud_servers_on_node = []
        cls.private_network = {'uuid': '11111111-1111-1111-1111-111111111111'}
        cls.public_network = {'uuid': '00000000-0000-0000-0000-000000000000'}
        cls.rackconnect_network = {'uuid': cls.rcv3_cloud_network}
        cls.min_servers = 1

        # Since RCV3 pools must be created by human intervention,
        # verify that at least one exists before proceeding with tests
        tenant_pools = cls.rcv3_client.list_pools().entity.pools
        if len(tenant_pools) == 0:
            raise Exception("No RCv3 pool configured.")

        # Mimic should have a single pool out of the box.
        # Note: Ideally, we want the same code path for both mimic and
        # real hardware.  However, since it requires human intervention to
        # create an RCv3 load balancer pool, we have to make the exception
        # to optimize our tests for each configuration here.
        #
        # rc_load_balancer_* are initialized in the base class,
        # AutoscaleFixture.
        cls.pool = None
        if cls.rcv3_load_balancer_pool['type'] == 'mimic':
            cls.pool = tenant_pools[0]
        else:
            # We're configured to run against actual hardware.
            for pool in tenant_pools:
                if pool.id == cls.rcv3_load_balancer_pool['loadBalancerId']:
                    cls.pool = pool

        lb_pools = [{'loadBalancerId': cls.pool.id, 'type': 'RackConnectV3'}]

        # Many tests require us to have some servers sitting in an account
        # ahead of time.  We don't actually use these servers for anything,
        # except to verify that Autoscale doesn't affect them in any way.  We
        # create a group and some servers in that group here.
        init_group_name = rand_name('as_rcv3_test-back')
        background_group_resp = cls.autoscale_behaviors.create_scaling_group_given(
            gc_name=init_group_name,
            gc_cooldown=1,
            gc_min_entities=2,
            lc_load_balancers=lb_pools,
            lc_networks=[cls.private_network, cls.rackconnect_network])
        cls.resources.add(background_group_resp.entity.id,
                          cls.autoscale_client.delete_scaling_group_with_force)

        # Create the cloud load balancers needed for testing before the
        # blocking wait for servers to build.
        #
        # We create these before waiting for the group to complete because it
        # lets us overlap load-balancer creation and server spin-up.  This lets
        # us use a single polling loop to effectively wait for both resources
        # to be up.  RISK: it depends on load balancers provisioning faster
        # than servers.
        cls.load_balancer_1_response = cls.lbaas_client.create_load_balancer('otter_test_1', [],
                                                                             'HTTP', 80, "PUBLIC")
        cls.load_balancer_1 = cls.load_balancer_1_response.entity.id
        cls.resources.add(cls.load_balancer_1, cls.lbaas_client.delete_load_balancer)

        # OK, back to waiting for servers to spin up.
        background_servers, err = cls.autoscale_behaviors.wait_for_servers_to_build(
            background_group_resp.entity.id,
            2,
            timeout=600)
        time.sleep(60)

        # If there was an error waiting for servers to build, abort the testing.
        if err:
            print "SetUpClass failed: background servers"

    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_scaling_group_with_pool_on_cloud_network(self):
        """
        Test that it is possible to create a scaling group with 0 entities
        connected to an RCV3 LB pool with a cloud_network specified.
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=0,
                                                  network_list=[self.rackconnect_network])
        self._common_scaling_group_assertions(pool_group_resp)

    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_scaling_group_with_pool_on_private(self):
        """
        Test that it is possible to create a scaling group with 0 entities
        connected to an RCV3 LB pool with only private network specified.
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=0,
                                                  network_list=[self.private_network])
        self._common_scaling_group_assertions(pool_group_resp)

    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_scaling_group_with_pool_on_public(self):
        """
        Test that it is possible to create a scaling group with 0 entities
        connected to an RCV3 LB pool with only private network specified
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=0,
                                                  network_list=[self.public_network])
        self._common_scaling_group_assertions(pool_group_resp)




    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_nonzero_scaling_group_with_pool_on_cloud_network(self):
        """
        Test that it is possible to create a scaling group with gc_min_entities_alt entities
        connected to an RCV3 LB pool with a cloud_network specified.
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.gc_min_entities_alt,
                                                  network_list=[self.rackconnect_network])
        self._common_scaling_group_assertions(pool_group_resp)
        self.wait_for_expected_number_of_active_servers(pool_group_resp.entity.id,
                                                        self.gc_min_entities_alt,
                                                        timeout=600)
        self.verify_group_state(pool_group_resp.entity.id, self.gc_min_entities_alt)

    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_nonzero_scaling_group_with_pool_on_private(self):
        """
        Test that it is possible to create a scaling group with self.gc_min_entities_alt entities
        connected to an RCV3 LB pool with only private network specified.
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.gc_min_entities_alt,
                                                  network_list=[self.private_network])
        self._common_scaling_group_assertions(pool_group_resp)
        self.wait_for_expected_number_of_active_servers(pool_group_resp.entity.id,
                                                        self.gc_min_entities_alt,
                                                        timeout=600)
        self.verify_group_state(pool_group_resp.entity.id, self.gc_min_entities_alt)

    @tags(speed='slow', type='rcv3')
    #@unittest.skip('')
    def test_create_nonzero_scaling_group_with_pool_on_public(self):
        """
        Test that it is possible to create a scaling group with self.gc_min_entities_alt entities
        connected to an RCV3 LB pool with only private network specified
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.gc_min_entities_alt,
                                                  network_list=[self.public_network])
        self._common_scaling_group_assertions(pool_group_resp)
        self.wait_for_expected_number_of_active_servers(pool_group_resp.entity.id,
                                                        self.gc_min_entities_alt,
                                                        timeout=600)
        self.verify_group_state(pool_group_resp.entity.id, self.gc_min_entities_alt)






    @tags(speed='slow', type='rcv3')
    @unittest.skip('')
    def test_create_scaling_group_with_pool_counts(self):
        """
        Test that it is possible to create a scaling group with min_servers servers
        connected to an RCv3 LB pool.

        This is a simple smoke test that only checks the node counts.
        """
        # This sleep is necessary because other tests have just completed, but
        # their resources haven't yet been completely freed up.  TODO(sfalvo):
        # See Github issue #855.
        time.sleep(240)

        # Capture the initial number of cloud servers on the node.
        # This is our baseline number of servers.
        init_cloud_servers = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']

        # Create a scaling group with a reasonable number of servers.
        # Ideally, this should, in no way whatsoever, affect our baseline servers.
        # We block until the servers are created (or until we timeout).
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.min_servers,
                                                  network_list=[self.rackconnect_network])
        self.wait_for_expected_number_of_active_servers(pool_group_resp.entity.id,
                                                        self.min_servers,
                                                        timeout=700)

        # Wait for rackconnect to reflect number of servers.  This is not a
        # polling loop since that would prevent overage detection.
        time.sleep(60)

        # Make sure that we have the correct number of cloud servers in our possession.
        new_counts = self._get_node_counts_on_pool(self.pool.id)
        expected_count_on_pool = init_cloud_servers + self.min_servers
        self.assertEqual(new_counts['cloud_servers'], expected_count_on_pool,
                         msg=('count of servers on lb pool {0} is not equal to '
                              'expected count ([{1}] + {2})').format(
                              new_counts['cloud_servers'], init_cloud_servers,
                              self.min_servers))

    @tags(speed='slow', type='rcv3')
    @unittest.skip('')
    def test_create_scaling_group_with_pool_and_nonzero_min(self):
        """
        Create group with min_entities servers, a single RCv3 LB, and a
        Rackconnect network.  After waiting for the number of servers to come
        up, we verify that the nova_server_id is in the list of servers on the
        node.  We also verify correct networks appear on the server.
        """
        # Create the group with some minimum number of nodes.
        networks = [self.rackconnect_network]
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.min_servers,
                                                  network_list=networks)
        pool_group = pool_group_resp.entity

        # Wait for the minumum servers to become active and
        # get list of server_ids on autoscale group
        active_server_list = self.wait_for_expected_number_of_active_servers(pool_group.id,
                                                                             self.min_servers,
                                                                             timeout=600)

        # Check that the server_ids on the scaling group match the server_ids on the RCV3 nodes
        pool_server_ids = self._get_cloud_server_ids_on_lb_pool_nodes(self.pool.id)
        for server in active_server_list:
            self.assertTrue(server in pool_server_ids)
            server_info_response = self.server_client.get_server(server)
            server_info = server_info_response.entity
            network_info_response = self.rcv3_client.get_cloud_network_info(
                self.rackconnect_network['uuid'])
            network_info = network_info_response.entity

            # Verify that our servers have the correct set of networks attached.
            self.assertTrue('private' in dir(server_info.addresses),
                            msg='server does not have a private network')
            self.assertTrue(network_info.name in dir(server_info.addresses),
                            msg='server RC network does not match RC config')

        # Our pool should be in active status, of course.  Anything else is an error.
        status = self.rcv3_client.get_pool_info(self.pool.id).entity.status
        self.assertEquals(status, "ACTIVE",
                          msg='LB Pool status {0} is not in expected ACTIVE state'.format(status))

    @tags(speed='slow', type='rcv3')
    @unittest.skip('')
    def test_scale_up_down_on_rcv3_pool(self):
        """
        Attempt to scale up and down on a correctly configured RCv3 pool.
        Since we expect scaling to proceed as instructed, we test both scaling
        directions.
        """
        lb_pools = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'}]

        # Capture a list of the node_ids of all nodes on the pool before doing anything
        initial_node_ids = []
        initial_node_list = self.rcv3_client.get_nodes_on_pool(self.pool.id).entity.nodes
        for each_node in initial_node_list:
            initial_node_ids.append(each_node.id)

        # Create the group used for testing The timeout bounds the length of
        # time needed to create the servers in Nova.  However....
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools,
                                                  group_min=self.min_servers,
                                                  network_list=[self.rackconnect_network])
        pool_group = pool_group_resp.entity
        self.wait_for_expected_number_of_active_servers(
            pool_group.id, self.min_servers, timeout=600)

        # ..., we still need to wait some more to allow their existence to
        # propegate through the rest of Autoscale's and Rackconnect V3's
        # infrastructure.  One minute ought to be enough for anyone.(tm)
        time.sleep(60)

        # Next, we get the initial nodes on each of the group's load balancers.
        # For this code to have any meaning, we assume EITHER (1) nobody else
        # uses the Rackconnect load balancer pool for the duration of this test,
        # or (2) the Rackconnect hardware belongs exclusively to the QE team
        # running this test (essentially fulfilling #1 anyway).
        initial_node_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']

        # Since at least the group_min node should be on the load_balancer, check that
        # the initial list of node ids is not empty
        self.assertTrue(initial_node_ids, msg='There were no initial nodes present on the loadbalancer')

        # Define a policy to scale up.
        scale_amt = 2
        policy_up_data = {'change': scale_amt, 'cooldown': 0}
        expected_server_count = initial_node_count + scale_amt
        as_server_count = self.min_servers + scale_amt

        # Register the policy and execute it immediately.
        self.autoscale_behaviors.create_policy_webhook(pool_group.id,
                                                       policy_up_data,
                                                       execute_policy=True)
        self.wait_for_expected_number_of_active_servers(
            pool_group.id,
            as_server_count)

        # Wait for propogation again
        time.sleep(60)

        # Get node count after scaling and confirm that the expected number of nodes are
        # present on the load_balancer_pool
        scale_up_node_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']
        self.assertEquals(scale_up_node_count, expected_server_count, msg='The actual '
                          'cloud_server count of [{0}] does not match the expected count '
                          'of [{1}]'.format(scale_up_node_count, expected_server_count))

        # Define a policy to scale down.
        policy_down_data = {'change': -scale_amt, 'cooldown': 0}
        expected_server_count = expected_server_count - scale_amt
        as_server_count = as_server_count - scale_amt

        # Register the policy and execute it immediately
        self.autoscale_behaviors.create_policy_webhook(pool_group.id,
                                                       policy_down_data,
                                                       execute_policy=True)
        self.wait_for_expected_number_of_active_servers(
            pool_group.id,
            as_server_count)

        # Wait for propogation again
        time.sleep(60)

        # Get node count after scaling and confirm that the expected number of nodes are
        # present on the load_balancer_pool
        scale_down_node_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']
        self.assertEquals(scale_down_node_count, expected_server_count, msg='The actual '
                          'cloud_server count of [{0}] does not match the expected count '
                          'of [{1}]'.format(scale_up_node_count, expected_server_count))

        # Capture a list of the node_ids of all nodes on the pool after scaling
        final_node_ids = []
        final_node_list = self.rcv3_client.get_nodes_on_pool(self.pool.id).entity.nodes
        for each_node in final_node_list:
            final_node_ids.append(each_node.id)

        for nid in initial_node_ids:
            self.assertTrue(nid in final_node_ids, msg='Initial node {0} was not in '
                            'the final list'.format(nid))

    @tags(speed='slow', type='rcv3')
    def test_scale_up_down_on_rcv3_and_clb(self):
        """As test_scale_up_down_on_rcv3, but includes a cloud load balancer as well."""
        # Define an RCV3 load_balancer_pool and a cloud load balancer to use in the test
        # For the CLB, assign a random port for robustness
        clb_port = random.randint(1000, 9999)
        load_balancers = [{'loadBalancerId': self.pool.id, 'type': 'RackConnectV3'},
                          {'loadBalancerId': self.load_balancer_1, 'port': clb_port}]

        # Capture a list of the node_ids of all nodes on the pool before doing anything.
        init_rc_node_ids = []
        initial_node_list = self.rcv3_client.get_nodes_on_pool(self.pool.id).entity.nodes
        for each_node in initial_node_list:
            init_rc_node_ids.append(each_node.id)

        initial_cloud_server_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']

        # Create the group used for testing The timeout bounds the length of
        # time needed to create the servers in Nova.  However....
        pool_group_resp = self._create_rcv3_group(lb_list=load_balancers,
                                                  group_min=self.min_servers,
                                                  network_list=[self.rackconnect_network,
                                                                self.private_network])
        pool_group = pool_group_resp.entity
        active_server_list = self.wait_for_expected_number_of_active_servers(
            pool_group.id, self.min_servers, timeout=600)

        # ..., we still need to wait some more to allow their existence to
        # propegate through the rest of Autoscale's and Rackconnect V3's
        # infrastructure.
        self.wait_for_expected_number_of_active_servers(
            pool_group.launchConfiguration.loadBalancers[0].loadBalancerId,
            initial_cloud_server_count + self.min_servers, timeout=300, api="RackConnect")

        # Next, we get the initial nodes on each of the group's load balancers.
        # For this code to have any meaning, we assume EITHER (1) nobody else
        # uses the Rackconnect load balancer pool for the duration of this test,
        # or (2) the Rackconnect hardware belongs exclusively to the QE team
        # running this test (essentially fulfilling #1 anyway).
        server_count_before_autoscaling = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']

        # Define a policy to scale up
        scale_amt = 2
        policy_up_data = {'change': scale_amt, 'cooldown': 0}
        expected_rcv3_server_count = server_count_before_autoscaling + scale_amt
        as_server_count = self.min_servers + scale_amt

        # Create the policy and execute it immediately
        self.autoscale_behaviors.create_policy_webhook(pool_group.id,
                                                       policy_up_data,
                                                       execute_policy=True)
        self.wait_for_expected_number_of_active_servers(
            pool_group.id,
            as_server_count)

        # Wait for RackConnect to reflect Otter's preferred configuration.
        server_list_after_scale_up = self.wait_for_expected_number_of_active_servers(
            pool_group.launchConfiguration.loadBalancers[0].loadBalancerId,
            expected_rcv3_server_count, timeout=300, api="RackConnect")

        # Get node count after scaling and confirm that the expected number of
        # nodes are present on the load_balancer_pool.
        scale_up_node_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']
        self.assertEquals(scale_up_node_count, expected_rcv3_server_count, msg='The actual '
                          'cloud_server count of [{0}] does not match the expected count '
                          'of [{1}]'.format(scale_up_node_count, expected_rcv3_server_count))

        # Define a policy to scale down
        policy_down_data = {'change': -scale_amt, 'cooldown': 0}
        expected_rcv3_server_count = expected_rcv3_server_count - scale_amt
        as_server_count = as_server_count - scale_amt

        # Create the policy and execute it immediately
        self.autoscale_behaviors.create_policy_webhook(pool_group.id,
                                                       policy_down_data,
                                                       execute_policy=True)
        server_list_after_scale_down = self.wait_for_expected_number_of_active_servers(
            pool_group.id, as_server_count)

        # Wait for propogation again
        self.wait_for_expected_number_of_active_servers(
            pool_group.launchConfiguration.loadBalancers[0].loadBalancerId,
            expected_rcv3_server_count, timeout=300, api="RackConnect")

        # Get node count after scaling and confirm that the expected number of nodes are
        # present on the load_balancer_pool
        scale_down_node_count = self._get_node_counts_on_pool(self.pool.id)['cloud_servers']
        self.assertEquals(scale_down_node_count, expected_rcv3_server_count, msg='The actual '
                          'cloud_server count of [{0}] does not match the expected count '
                          'of [{1}]'.format(scale_up_node_count, expected_rcv3_server_count))

        # Capture a list of the node_ids of all nodes on the pool after scaling
        final_node_ids = []
        final_node_list = self.rcv3_client.get_nodes_on_pool(self.pool.id).entity.nodes
        for each_node in final_node_list:
            final_node_ids.append(each_node.id)

        # Verify Autoscale didn't interfere with our initial, existing set of servers.
        for nid in init_rc_node_ids:
            self.assertTrue(nid in final_node_ids, msg='Initial node {0} was not in '
                            'the final list'.format(nid))

    def _get_node_counts_on_pool(self, pool_id):
        """
        Get the node counts on a given pool.  Takes an ID string.
        Returns a dictionary with cloud_servers, external, and total
        members.  Total contains the sum of the former two fields.
        cloud_servers counts the number of Rackspace cloud servers, while
        external counts everything but (e.g., dedicated servers).
        """
        print "%g _get_node_counts_on_pool(447)(self, %s)" % (time.time(), pool_id)
        return self.rcv3_client.get_pool_info(pool_id).entity.node_counts

    def _get_cloud_servers_on_pool(self, pool_id):
        """
        Return a list of the cloud server nodes on the specified pool,
        identified by pool_id.
        """
        def as_hash(n):
            return {'server_id': n.cloud_server['id'], 'node_id': n.id}

        node_list = self.rcv3_client.get_nodes_on_pool(pool_id).entity.nodes
        return [as_hash(n) for n in node_list if safe_hasattr(n, 'cloud_server')]

    def _get_cloud_server_ids_on_lb_pool_nodes(self, pool_id):
        """Return a list of all cloud server ids on the given lb pool_id."""
        return [s['server_id'] for s in self._get_cloud_servers_on_pool(pool_id)]

    def _create_rcv3_group(self, lb_list=None, group_min=None, network_list=None):
        """
        Create a scaling group.  The group created will automatically be added
        to the object's set of resources reclaimed automatically upon
        destruction.

        This method has several side-effects in addition to creating the group.
        Attributes with the gc_ prefix refer to various group config settings
        of the group.  lc_ prefixed attributes correspond to their eponymous
        attributes in the launchConfig.  In particular, the following fields
        are set or reset prior to group creation:

            self.gc_name           Set to a random value.
            self.gc_max_entities   Forced to 10.
            self.gc_metadata       Set to a trivial, yet non-empty, dictionary.
            self.lc_metadata       As with gc_metadata.
            self.lc_disk_config    Forced to 'AUTO'.
            self.lc_networks       Set to the value of network_list.

        The following attributes are used as inputs to the group creation
        process, although they're not specified in the method's argument list.

            self.gc_min_entities  (only if group_min is falsy.)
            self.lc_name
            self.lc_image_ref
            self.lc_flavor_ref

        Thus, make sure these attributes are set _prior_ to calling
        _create_rcv3_group().
        """
        group_min = group_min or self.gc_min_entities

        self.gc_name = rand_name('as_rcv3_test-group')
        self.gc_max_entities = 10
        self.gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                            'gc_meta_key_2': 'gc_meta_value_2'}
        self.lc_metadata = {'meta_key_1': 'meta_value_1',
                            'meta_key_2': 'meta_value_2'}
        self.lc_disk_config = 'AUTO'
        self.lc_networks = network_list

        self.create_resp = self.autoscale_client.create_scaling_group(
            gc_name=self.gc_name,
            gc_cooldown=0,
            gc_min_entities=group_min,
            gc_max_entities=self.gc_max_entities,
            gc_metadata=self.gc_metadata,
            lc_name=self.lc_name,
            lc_image_ref=self.lc_image_ref,
            lc_flavor_ref=self.lc_flavor_ref,
            lc_metadata=self.lc_metadata,
            lc_disk_config=self.lc_disk_config,
            lc_networks=self.lc_networks,
            lc_load_balancers=lb_list)
        pool_group = self.create_resp.entity
        self.resources.add(pool_group.id,
                           self.autoscale_client.delete_scaling_group_with_force)
        return self.create_resp

    def _common_scaling_group_assertions(self, pool_group_resp):
        pool_group = pool_group_resp.entity
        self.assertTrue(pool_group_resp.ok,
                        msg='Create scaling group call failed with API Response: {0} for '
                        'group {1}'.format(pool_group_resp.content, pool_group.id))
        self.assertEquals(self.create_resp.status_code, 201,
                          msg='The create failed with {0} for group '
                          '{1}'.format(pool_group_resp.status_code, pool_group.id))
        self.assertEquals(pool_group.launchConfiguration.loadBalancers[0].loadBalancerId,
                          self.pool.id,
                          msg='The launchConfig for group {0} did not contain the load balancer'
                          .format(pool_group.id))
        self.assertEquals(pool_group.launchConfiguration.loadBalancers[0].type, "RackConnectV3",
                          msg='Load balancer type {0} is not correct for RackConnect pools'
                          .format(pool_group.launchConfiguration.loadBalancers[0].type))
