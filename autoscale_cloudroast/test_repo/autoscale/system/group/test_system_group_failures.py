"""
System tests for multiple scaling groups when encountering upstream errors
"""
import json
import time

from cafe.drivers.unittest.decorators import tags

from test_repo.autoscale.fixtures import AutoscaleFixture


class GroupFixtureNovaFailures(AutoscaleFixture):

    """
    System tests to verify scaling group scenarios when upstream Nova errors
    """

    @tags(requires='mimic')
    def test_system_create_group_create_server_fails(self):
        """
        If a scaling group is created with a min. entity of 1, the group
        starts off with a pending capacity of 1.  But when creating the
        server fails, the group will end up with up with a pending capacity of
        0.
        """
        error = {
            "message": "This is a simulated nova error",
            "code": 500
        }

        lc_metadata = {'create_server_failure': json.dumps(error)}

        create_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=1,
            lc_metadata=lc_metadata)
        self.assertEquals(create_response.status_code, 201)
        group = create_response.entity
        self.resources.add(group, self.empty_scaling_group)

        # wait to give it otter time to become consistent, so this doesn't
        # pass by accident
        time.sleep(1)

        self.wait_for_expected_group_state(group.id, 0)

