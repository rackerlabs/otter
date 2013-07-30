"""
System tests for multiple scaling groups scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import base64


class GroupFixture(AutoscaleFixture):

    """
    System tests to verify scaling group scenarios
    """

    def test_system_update_minentities_to_scaleup(self):
        """
        The scaling group scales up when the minentities are updated,
        to be more than 0
        """
        minentities = 0
        group = self._create_group(minentities=minentities)
        self.verify_group_state(group.id, minentities)
        upd_minentities = 3
        self._update_group(group=group, minentities=upd_minentities)
        self.verify_group_state(group.id, upd_minentities)
        self.empty_scaling_group(group)

    def test_system_update_minentities_to_be_lesser_than_during_create_group(self):
        """
        The scaling group does not scale down when the minenetities are updated,
        to be lower than when created
        """
        minentities = 4
        group = self._create_group(minentities=minentities)
        self.verify_group_state(group.id, minentities)
        upd_minentities = 1
        self._update_group(group=group, minentities=upd_minentities)
        self.verify_group_state(group.id, minentities)
        self.empty_scaling_group(group)

    def test_system_update_maxentities_less_than_desiredcapacity(self):
        """
        Create a scaling group and execute a policy to be within maxentities,
        reduce the max entities to be less than the active servers (desiredCapacity)
        and the scaling group scales down to match the updated maxentities
        """
        minentities = 0
        maxentities = 10
        splist = [{
            'name': 'scale up by 2',
            'change': 2,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(minentities=minentities,
                                   maxentities=maxentities,
                                   splist=splist)
        policy = self._execute_policy(group)
        self.verify_group_state(group.id, policy['change'])
        upd_maxentities = 1
        self._update_group(group=group, maxentities=upd_maxentities)
        self.verify_group_state(group.id, upd_maxentities)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=upd_maxentities)
        self.empty_scaling_group(group)

    def test_system_update_maxenetities_and_execute_policy(self):
        """
        Execute policy on scaling group such that the maxentities are met,
        update the maxentities and upon re-executing the scaling policy beyond
        the older maxentities, the scaling group scales up
        """
        minentities = 0
        maxentities = 2
        cooldown = 0
        splist = [{
            'name': 'scale up by 5',
            'change': 5,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(minentities=minentities,
                                   maxentities=maxentities,
                                   cooldown=cooldown,
                                   splist=splist)
        policy = self._execute_policy(group)
        self.verify_group_state(group.id, maxentities)
        upd_maxentities = 10
        self._update_group(group=group, maxentities=upd_maxentities)
        policy = self._execute_policy(group)
        total_servers = maxentities + policy['change']
        self.verify_group_state(group.id, total_servers)
        self.empty_scaling_group(group)

    def test_system_group_cooldown_enforced_when_reexecuting_same_policy(self):
        """
        The group cooldown is enforced when executing a scaling policy
        with zero policy cooldown, multiple times
        """
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(splist=splist)
        policy = self._execute_policy(group)
        reexecute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(reexecute_policy_response.status_code, 403,
                          msg='scaling policy failed execution with status {0}'
                          ' for group {1}'
                          .format(reexecute_policy_response.status_code, group.id))
        self.verify_group_state(group.id, policy['change'])
        self.empty_scaling_group(group)

    def test_system_group_cooldown_enforced_when_executing_different_policies(self):
        """
        The group cooldown is enforced when executing different scaling policies,
        multiple times
        """
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(splist=splist)
        policy2 = self.autoscale_behaviors.create_policy_min(group_id=group.id)
        policy = self._execute_policy(group)
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 403,
                          msg='scaling policy failed execution with status {0}'
                          ' for group {1}'
                          .format(execute_policy2_response.status_code, group.id))
        self.verify_group_state(group.id, policy['change'])
        self.empty_scaling_group(group)

    def test_systemupdate_group_cooldown_and_execute_policy(self):
        """
        Different scaling policies can be executed when the group cooldown
        is updated to be 0
        """
        minentities = 2
        cooldown = 60
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(minentities=minentities,
                                   cooldown=cooldown,
                                   splist=splist)
        self.verify_group_state(group.id, minentities)
        policy2 = self.autoscale_behaviors.create_policy_min(group_id=group.id)
        policy = self._execute_policy(group)
        self.verify_group_state(group.id, minentities + policy['change'])
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 403,
                          msg='scaling policy failed execution with status {0}'
                          ' for group {1}'
                          .format(execute_policy2_response.status_code, group.id))
        self._update_group(group=group, cooldown=0)
        execute_policy2_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy2['id'])
        self.assertEquals(execute_policy2_response.status_code, 202,
                          msg='policy failed execution even with group cooldown 0, with status {0}'
                          ' for group {1}'
                          .format(execute_policy2_response.status_code, group.id))
        total_servers = policy2[
            'change'] + group.groupConfiguration.minEntities + policy['change']
        self.verify_group_state(group.id, total_servers)
        self.empty_scaling_group(group)

    def test_system_execute_policy_beyond_maxentities(self):
        """
        Scaling policy is executed when change + minentities > maxentities, upto
        the maxentities. Re-executing policy when maxentities are met fails with 403.
        The scaling policy can be executed when the maxentities is updated to be higher.
        """
        minentities = 2
        maxentities = 3
        cooldown = 0
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(
            minentities=minentities, maxentities=maxentities,
            cooldown=cooldown, splist=splist)
        self.verify_group_state(group.id, minentities)
        policy = self._execute_policy(group)
        self.verify_group_state(group.id, maxentities)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='Policy was executed even when max entities were met,'
                          'with status {0} for group {1}'
                          .format(execute_policy_response.status_code, group.id))
        upd_maxentities = 10
        self._update_group(group=group, maxentities=upd_maxentities)
        self._execute_policy(group)
        total_servers = maxentities + policy['change']
        self.verify_group_state(group.id, total_servers)
        self.empty_scaling_group(group)

    def test_system_execute_policy_beyond_maxentities_when_min_equals_max(self):
        """
        Scaling group with minentities = maxentities cannot execute scale up
        policy. Update the maxentities and the scaling policy can be executed.
        """
        minentities = 2
        maxentities = 2
        splist = [{
            'name': 'scale up by 3',
            'change': 3,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group = self._create_group(
            minentities=minentities, maxentities=maxentities,
            splist=splist)
        self.verify_group_state(group.id, minentities)
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='policy was executed even when max entities were met, with status {0}'
                          ' for group {1}'
                          .format(execute_policy_response.status_code, group.id))
        upd_maxentities = 10
        self._update_group(group=group, maxentities=upd_maxentities)
        policy = self._execute_policy(group)
        total_servers = maxentities + policy['change']
        self.verify_group_state(group.id, total_servers)
        self.empty_scaling_group(group)

    def test_system_create_scaling_group_with_same_attributes(self):
        """
        Scaling groups can be created with the exact same attributes
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
        self.resources.add(group1.id,
                           self.autoscale_client.delete_scaling_group)
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
        group2 = create_group2_response.entity
        self.resources.add(group2.id,
                           self.autoscale_client.delete_scaling_group)
        self.empty_scaling_group(group1)
        self.empty_scaling_group(group2)

    def _create_group(self, minentities=None, maxentities=None, cooldown=None,
                      splist=None):
        """
        Create a scaling group with the given minentities, maxentities, cooldown
        and scaling policy and Return the group.
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities, gc_max_entities=maxentities,
            gc_cooldown=cooldown, sp_list=splist)
        group = create_group_response.entity
        self.assertEqual(create_group_response.status_code, 201,
                         msg='Create group failed with {0}'.format(group.id))
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group

    def _update_group(self, group, minentities=None, maxentities=None,
                      cooldown=None):
        """
        Update the scaling group's minentities, maxenetities or cooldown and
        assert the update was successful.
        """
        if minentities is None:
            minentities = group.groupConfiguration.minEntities
        if maxentities is None:
            maxentities = group.groupConfiguration.maxEntities
        if cooldown is None:
            cooldown = group.groupConfiguration.cooldown
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=cooldown,
            min_entities=minentities,
            max_entities=maxentities,
            metadata={})
        self.assertEqual(update_group.status_code, 204,
                         msg='Update group failed with {0} for group {1}'.format(
                         update_group.status_code, group.id))

    def _execute_policy(self, group):
        """
        Execute the scaling policy on the group, assert it was successfull and
        return the policy.
        """
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='scaling policy failed execution with status {0}'
                          ' for group {1}'.format(execute_policy_response.status_code,
                                                  group.id))
        return policy
