"""
Test the non-scenario specific audit log functions.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class AuditLogBasicsTest(AutoscaleFixture):
    """
    Verify the following basic audit log behaviors:
        1.) Using GET on /tenantid/history returns 200 and result OK
        2.) Each entry has the following fields: timestamp, message, event_type, scaling_group_id
    """

    @classmethod
    def setUpClass(cls):
        """
        Create scaling groups to populate the history log
        """
        super(AuditLogBasicsTest, cls).setUpClass()
        first_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.first_scaling_group = first_group.entity
        second_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.second_scaling_group = second_group.entity
        third_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.third_scaling_group = third_group.entity
        # Delete the first scaling group for variety
        cls.autoscale_client.delete_scaling_group(cls.first_scaling_group.id)
        cls.resources.add(cls.second_scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.resources.add(cls.third_scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)

    def test_history_resource_response(self):
        """
        Verify that querying the history API returns the expected response.
        """
        # Confirm that the request response is 200
        history_response = self.autoscale_client.get_history()
        self.assertTrue(history_response.ok,
                        msg='The history query failed with: API Response {0} for '
                        'tenant {1}'.format(history_response.content, self.tenant_id))
        self.assertEquals(history_response.status_code, 200,
                          msg='The history request failed with {0} for tenant '
                          '{1}'.format(history_response.status_code, self.tenant_id))
        # Extract the list of events
        latest_event = (history_response.entity).events[0]
        # Confirm that the basic fiels are present for the most recent events
        self.assertTrue(hasattr(latest_event, 'timestamp'))
        self.assertTrue(hasattr(latest_event, 'message'))
        self.assertTrue(hasattr(latest_event, 'event_type'))
        self.assertTrue(hasattr(latest_event, 'scaling_group_id'))
