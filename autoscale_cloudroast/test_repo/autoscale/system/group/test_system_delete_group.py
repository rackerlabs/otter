"""
System tests for delete scaling group
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture
import unittest
#from time import sleep


class DeleteGroupTest(ScalingGroupFixture):

    """
    System tests to verify various delete scaling group scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group
        """
        cls.minentities = 2
        super(DeleteGroupTest, cls).setUpClass(
            gc_min_entities=cls.minentities)

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(DeleteGroupTest, cls).tearDownClass()

    def test_system_delete_group_with_minentities_over_zero(self):
        """
        Verify delete scaling group when minentities more than zero
        """
        # cannot delete such a group but this fails in dev vm currently due to AUTO - 284
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            self.minentities,
            msg='Active + Pending servers over min entities')
        self.assertEqual(group_state.desiredCapacity, self.minentities,
                         msg='Desired capacity not same as min entities upon group creation')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group while servers were building on the group')

    def test_system_delete_group_update_minentities_to_zero(self):
        """
        Verify delete scaling group when minenetities of the group are updated to be zero
        """
        minentities = 0
        reduce_group_size_response = self.autoscale_client.update_group_config(
            group_id=self.group.id, name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=minentities,
            max_entities=self.group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(reduce_group_size_response.status_code, 204,
                          msg='Update to 0 minentities failed with reason %s'
                          % reduce_group_size_response.content)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            self.minentities,
            msg='Active + Pending servers over min entities')
        self.assertEqual(group_state.desiredCapacity, self.minentities,
                         msg='Desired capacity not same as min entities upon group creation')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group was unsuccessful %s'
                          % delete_group_response.content)

    def test_system_delete_group_with_zero_minentities(self):
        """
        Verify delete scaling group with zero minenetities
        """
        minentities = 0
        group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        group = group_response.entity
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.desiredCapacity,
            minentities,
            msg='Desired capacity does not match zero minentities')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Deleted group failed even when group was empty')

    def test_system_delete_group_zero_minentities_execute_webhook(self):
        """
        Verify delete group when group has 0 minentities and webhook has been executed.
        Note : Failing in dev vm cause group state is updating late
        """
        minentities = 0
        sp_list = [{
            'name': 'scale up by 2',
            'change': 2,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            sp_list=sp_list)
        group = group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        webhook_response = self.autoscale_client.create_webhook(
            group_id=group.id,
            policy_id=policy['id'],
            name='testit')
        webhook = self.autoscale_behaviors.get_webhooks_properties(
            webhook_response.entity)
        execute_policy = self.autoscale_client.execute_webhook(
            webhook['links'].capability)
        self.assertEquals(execute_policy.status_code, 202)
        #sleep(5)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.desiredCapacity,
            policy['change'],
            msg='Desired capacity does not match scale up that was executed')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group while servers were building on the group')

    def test_system_delete_group_zero_minentities_execute_policy(self):
        """
        Verify delete scaling group when group has 0 minentities and policy has been executed.
        """
        minentities = 0
        sp_list = [{
            'name': 'scale up by 2',
            'change': 2,
            'cooldown': 0,
            'type': 'webhook'
        }]
        group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            sp_list=sp_list)
        group = group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy.status_code, 202)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.desiredCapacity,
            policy['change'],
            msg='scaling policy executed, but desired capacity does not match')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group while servers were building on the group')
