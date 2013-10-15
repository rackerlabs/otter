"""
System tests for force delete scaling group
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags


class ForceDeleteGroupTest(AutoscaleFixture):

    """
    System tests to verify various force delete scaling group scenarios
    """

    @tags(speed='slow')
    def test_system_force_delete_group_with_minentities_over_zero(self):
        """
        Force deleting a scaling group with active servers, updates the desired capacity to be 0,
        by deleting all the servers and then deletes the group.
        """
        group = self._create_group_given_minentities(self.gc_min_entities_alt)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        delete_group_response = self.autoscale_client.delete_scaling_group(group.id, 'true')
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Could not force delete group {0} when active servers existed '
                          'on it '.format(group.id))
        self.assert_servers_deleted_successfully(group.launchConfiguration.server.name)

    @tags(speed='quick')
    def test_system_force_delete_group_with_force_as_false_with_0_minentities(self):
        """
        Force deleting a scaling group with active servers with force set to true, deletes the group
        only if there are no active servers on the group.
        """
        group = self._create_group_given_minentities(self.gc_min_entities)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        delete_group_response = self.autoscale_client.delete_scaling_group(group.id, 'false')
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Force delete group {0} failed when there are no activer servers '
                          'on the group and force is set to false'.format(group.id))

    @tags(speed='quick')
    def test_system_force_delete_group_with_force_as_false_with_minentities(self):
        """
        Force deleting a scaling group with active servers with force set to false, deletes the group
        when there are no active servers on the group.
        """
        group = self._create_group_given_minentities(self.gc_min_entities_alt)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        delete_group_response = self.autoscale_client.delete_scaling_group(group.id, 'false')
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Force deleted group {0} when active servers existed '
                          'on it and force was set to false'.format(group.id))

    @tags(speed='quick')
    def test_system_force_delete_group_with_invalid_force_attribute(self):
        """
        Force deleting a scaling group with active servers with force set to invalid characters,
        does not result in error 500.
        """
        group = self._create_group_given_minentities(self.gc_min_entities_alt)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        params = ['True', 'False', True, False, 0, '']
        for each_param in params:
            delete_group_response = self.autoscale_client.delete_scaling_group(group.id, each_param)
            self.assertEquals(delete_group_response.status_code, 403,
                              msg='Force deleted group {0} when active servers existed '
                              'on it and force was set to invalid option'.format(group.id))

    def _create_group_given_minentities(self, minentities):
        """
        Create a scaling group with the given minEntities
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        self.assertEquals(create_group_response.status_code, 201)
        group = create_group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group
