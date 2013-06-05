"""
System tests for multiple scaling groups scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import base64
import unittest


class GroupFixture(AutoscaleFixture):

    """
    System tests to verify scaling group scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(GroupFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(GroupFixture, cls).tearDownClass()

    def test_system_update_minentities_to_scaleup(self):
        """
        Verify scale up when minentities is increased. AUTO-336
        """
        minentities = 0
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        group = create_group_response.entity
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            minentities,
            msg='Active + Pending servers is not equal to the minentities on the group')
        self.assertEqual(group_state.desiredCapacity, minentities,
                         msg='Desired capacity is not equal to the minentities on the group')
        upd_minentities = 3
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=upd_minentities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            upd_minentities,
            msg='Active + Pending servers is not equal to the minentities on the group')
        self.assertEqual(group_state.desiredCapacity, upd_minentities,
                         msg='Desired capacity is not equal to the minentities on the group')

    def test_system_update_minentities_to_be_lesser_than_during_create_group(self):
        """
        Verify scaling group when minentities is reduced. Note: scale down will not occur
        """
        minentities = 4
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        group = create_group_response.entity
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            minentities,
            msg='Active + Pending servers is not equal to the minentities on the group')
        self.assertEqual(group_state.desiredCapacity, minentities,
                         msg='Desired capacity is not equal to the minentities on the group')
        upd_minentities = 1
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=upd_minentities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            minentities,
            msg='Active + Pending servers is not equal to the minentities on the group')
        self.assertEqual(group_state.desiredCapacity, minentities,
                         msg='Desired capacity is not equal to the minentities on the group')

    def test_system_update_maxentities_less_than_desiredcapacity(self):
        """
        Verify group when max entities is updated to be less than current active servers
        """
        minentities = 0
        maxentities = 10
        splist = [{
            'name': 'scale up by 2',
            'change': 2,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            policy['change'],
            msg='Active + Pending servers is not equal to the change in the policy')
        self.assertEqual(group_state.desiredCapacity, policy['change'],
                         msg='Desired capacity is not equal to the change in the policy')
        upd_maxentities = 1
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=upd_maxentities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            upd_maxentities,
            msg='Active + Pending servers is not equal to the minentities on the group')
        self.assertEqual(group_state.desiredCapacity, upd_maxentities,
                         msg='Desired capacity is not equal to the minentities on the group')
        servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=upd_maxentities)
        self.assertEquals(len(servers_list), upd_maxentities,
                          msg='The total servers are over the max entities when scaling down')

    def test_system_update_maxenetities_and_execute_policy(self):
        """
        Verify execute policy after maxentities is updated
        """
        minentities = 0
        maxentities = 2
        splist = [{
            'name': 'scale up by 5',
            'change': 5,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            gc_cooldown=0,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            maxentities,
            msg='Active + Pending servers is not equal to maxentities')
        self.assertEqual(group_state.desiredCapacity, maxentities,
                         msg='Desired capacity is not equal maxentities')
        upd_maxentities = 10
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=upd_maxentities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        total_servers = maxentities + policy['change']
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            total_servers,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, total_servers,
                         msg='Desired capacity is not equal to expected number of servers')

    def test_system_group_cooldown_enforced_when_reexecuting_same_policy(self):
        """
        Verify same policy cannot be re-executed during scaling group cooldown
        """
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=30,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            policy['change'],
            msg='Active + Pending servers is not equal to the change in the policy')
        self.assertEqual(group_state.desiredCapacity, policy['change'],
                         msg='Desired capacity is not equal to the change in the policy')
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)

    def test_system_group_cooldown_enforced_when_executing_different_policies(self):
        """
        Verify different policies cannot be executed during scaling group cooldown AUTO-336
        prod group : d3aa8e57-396e-417d-a0ed-fed593630886, created 2 instead of 3
        """
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=30,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        policy2 = self.autoscale_behaviors.create_policy_min(group_id=group.id)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 403,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy2_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            policy['change'],
            msg='Active + Pending servers is not equal to the change in the first policy')
        self.assertEqual(group_state.desiredCapacity, policy['change'],
                         msg='Desired capacity is not equal to the change in the first policy')

    def test_system_update_group_cooldown_and_execute_policy(self):
        """
        Verify execute policy when group cooldown is updated to be Zero AUTO-336
        prod: group ea5fecb2-3696-424d-b639-e47706752b75 got 5 instead of 6
        """
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=2,
            gc_cooldown=30,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        policy2 = self.autoscale_behaviors.create_policy_min(group_id=group.id)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 403,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy2_response.status_code)
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=0,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 202,
                          msg='policy failed execution even with group cooldown 0, with status %s'
                          % execute_policy2_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        total_servers = policy2[
            'change'] + group.groupConfiguration.minEntities + policy['change']
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            total_servers,
            msg='Active + Pending servers is not equal to the expected number of servers')
        self.assertEqual(group_state.desiredCapacity, total_servers,
                         msg='Desired capacity is not equal to the expected number of servers')

    def test_system_execute_policy_beyond_maxentities(self):
        """
        Verify execute policy when executed multiple times to exceed maxentities
        """
        minentities = 2
        maxentities = 3
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            gc_cooldown=0,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='policy was executed even when max entities were met, with status %s'
                          % execute_policy_response.status_code)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='policy was executed even when max entities were met, with status %s'
                          % execute_policy_response.status_code)
        upd_maxentities = 10
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=upd_maxentities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        total_servers = maxentities + policy['change']
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            total_servers,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, total_servers,
                         msg='Desired capacity is not equal to expected number of servers')

    @unittest.skip("Min cannot be equal to max issue")
    def test_system_execute_policy_beyond_maxentities_when_min_equals_max(self):
        """
        Verify execute policy to exceed maxentities when group has min equal to max
        """
        minentities = 2
        maxentities = 2
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            gc_cooldown=0,
            sp_list=splist)
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
            msg='Scaling group with min=max not created because %s'
            % create_group_response.content)
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='policy was executed even when max entities were met, with status %s'
                          % execute_policy_response.status_code)
        upd_maxentities = 10
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=upd_maxentities,
            metadata={})
        self.assertEquals(update_group.status_code, 204)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        total_servers = maxentities + policy['change']
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            total_servers,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, total_servers,
                         msg='Desired capacity is not equal to expected number of servers')

    def test_system_create_scaling_group_with_same_attributes(self):
        """
        Verify two scaling groups can have the same attributes
        """
        gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                       'gc_meta_key_2': 'gc_meta_value_2'}
        file_contents = 'This is a test file.'
        lc_personality = [{'path': '/root/.csivh',
                           'contents': base64.b64encode(file_contents)}]
        lc_metadata = {'meta_key_1': 'meta_value_1',
                       'meta_key_2': 'meta_value_2'}
        lc_disk_config = 'AUTO'
        lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'},
                       {'uuid': '00000000-0000-0000-0000-000000000000'}]
        lc_load_balancers = [{'loadBalancerId': 9099, 'port': 8080}]
        sp_list = [{
            'name': 'scale up by 1',
            'change': 1,
            'cooldown': 100,
            'type': 'webhook'}]
        create_group1_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_metadata=gc_metadata,
            lc_personality=lc_personality,
            lc_metadata=lc_metadata,
            lc_disk_config=lc_disk_config,
            lc_networks=lc_networks,
            lc_load_balancers=lc_load_balancers,
            sp_list=sp_list)
        self.assertEquals(create_group1_response.status_code, 201)
        group1 = create_group1_response.entity
        create_group2_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_name=group1.groupConfiguration.name,
            gc_metadata=gc_metadata,
            lc_personality=lc_personality,
            lc_metadata=lc_metadata,
            lc_disk_config=lc_disk_config,
            lc_networks=lc_networks,
            lc_load_balancers=lc_load_balancers,
            sp_list=sp_list)
        self.assertEquals(create_group2_response.status_code, 201)
