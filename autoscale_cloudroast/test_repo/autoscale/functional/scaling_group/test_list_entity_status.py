"""
Test to create and verify the state of the group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest


class GetListEntityStatusTest(AutoscaleFixture):
    """
    Verify list group state.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(GetListEntityStatusTest, cls).setUpClass()
        cls.gc_max_entities = 10
        group_response = cls.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=cls.gc_min_entities_alt,
            gc_max_entities=cls.gc_max_entities)
        cls.group = group_response.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.group_state_response = cls.autoscale_client.list_status_entities_sgroups(
            cls.group.id)
        cls.group_state = cls.group_state_response.entity

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(GetListEntityStatusTest, cls).tearDownClass()

    def test_entity_status_response(self):
        """
        Verify list status' response code is 200, header.
        """
        self.assertEquals(200, self.group_state_response.status_code,
                          msg='The list entities call failed with {0}'
                          .format(self.group_state_response.status_code))
        self.validate_headers(self.group_state_response.headers)

    def test_entity_status(self):
        """
        Verify list status' data.
        """
        self.assertEquals(len(self.group_state.active), self.group_state.activeCapacity)
        self.assertEquals(self.group_state.desiredCapacity,
                          self.group_state.activeCapacity + self.group_state.pendingCapacity)
        self.assertEquals(self.group_state.paused, False,
                          msg='The scaling group status is paused upon creation')
        self.assertGreaterEqual(self.group_state.desiredCapacity, self.gc_min_entities_alt,
                                msg='Less than required number of servers in desired capacity')
        self.assertLessEqual(self.group_state.desiredCapacity, self.gc_max_entities,
                             msg='Total server count is over maxEntities')
