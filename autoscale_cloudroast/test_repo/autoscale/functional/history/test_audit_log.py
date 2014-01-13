"""
Test the non-scenario specific audit log functions.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class AuditLogBasicsTest(AutoscaleFixture):
    """
    Verify the following basic audit log behaviors:
        1.) Using GET on /tenantid/history returns 200 and result OK
            > what happens if you try PUT
        2.) Entry pagination
        3.) Only events for the given tenant ID are shown (security)
        4.) Transaction ID is unique?
        5.) log entries still present after group is deleted? (might be in different category)

    Prerequisites:
        1.) Tenant ID for an account with


    """

#    @classmethod
#    def setUpClass(cls):
#        """
#        TBD
#        """
#        pass


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
        expected_event = {'event_type': 'request.group.create.ok',
                          'user_id': self.tenant_id,
                          'scaling_group_id': self.scaling_group.id,
                          'event_status': 'TBD',
                          'parent_id': 'TBD',
                          'as_user_id': 'TBD',
                          'lc_name': self.autoscale_config.lc_name,
                          'gc_name': self.gc_name}
        # What set of data needs to be checked to conclude 'data' = request object?
        #TODO - NOTE: Using a response object strips the "type: launch_server" field from the
        #               launchConfiguration

        # Confirm that the most recent entry indicates a group was created successfully
        # Based on API functionality, assume that the first item in the list is the most recent
        self.assertEquals(latest_event.event_type, expected_event['event_type'],
                          msg='The event_type: {0} did not match the expected '
                          'event_type: {1}'.format(latest_event.event_type,
                                                   expected_event['event_type']))
        # Confirm event details match expected
        self.assertEqual(latest_event.data.launchConfiguration.server.name,
                         expected_event['lc_name'],
                         msg='Server name in the launch config history did not match the request')
        self.assertEqual(latest_event.data.groupConfiguration.name,
                         expected_event['gc_name'],
                         msg='The name in the group config history did not match the request')

    Categories:
    Requests (simple, ok)
    Requests (simple, fail)
    Convergence
        (Various cases that trigger convergence)
        > Test that when it converges it is logged correctly, not that convergence happens when it should
    Server
        (number of server.active entries matches the number of servers)
        Confirm there is no way to spin up or down a server without it being logged
    Error Injection
        > simulate externally triggered errors



> Complex Use case


When would audit logs be considered broken:
> unable to get logs
> not all events logged
> log entries present after deletion
> no way to modify logs




