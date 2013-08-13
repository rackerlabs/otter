"""
                  _A
                .'`"`'.
               /   , , \
              |   <\^/> |
              |  < (_) >|
              /===</V\>=\
             (.---._ _.-.)
              |/   a` a |
              (      _\ |
               \    __  ;
               |\   .  /
            _.'\ '----;'-.
        _.-'  O ;-.__.'\O `o.
       /o \      \/-.-\/|    \
      |    ;,     '.|\| /

This is the utility stuff for working with Bobby.

"""

import json

from otter.util.http import (append_segments, check_success,
                             wrap_request_error)


class BobbyClient(object):
    """
    Client for Bobby
    """

    def __init__(self, server_endpoint, treq_client=None):
        """
        Create a Bobby Client

        :param server_endpoint: Endpoint to use
        """
        self.server_endpoint = server_endpoint
        self.treq_client = treq_client
        if self.treq_client is None:
            import treq
            self.treq_client = treq

    def create_policy(self, tenant_id, group_id, policy_id, check_template, alarm_template):
        """
        Create a policy in Bobby.  This means that Bobby will start to roll out
        alarms and checks across all of the servers that are present.

        You need to create the group before you can create a policy or server in it.

        :param tenant_id: The tenant ID of the policy to create in Bobby

        :param group_id: The group ID of the scaling group to create in Bobby

        :param policy_id: The policy ID of the scaling policy we are creating

        :param check_template: A ``dict`` that contains the check check_template

        :param alarm_template: A string containing the alarm DSL

        :return: a ``dict`` containing the policy object on Bobby's end if successful.
            returns an errorback if the response is not a 201 Created.
        """
        payload = {
            'alarmTemplate': alarm_template,
            'checkTemplate': check_template,
            'policyId': policy_id
        }
        d = self.treq_client.post(append_segments(self.server_endpoint, tenant_id, 'groups',
                                                  group_id, 'policies'),
                                  data=json.dumps(payload))
        d.addCallback(check_success, [201])
        d.addErrback(wrap_request_error, self.server_endpoint, 'create_policy')
        return d.addCallback(self.treq_client.json_content)

    def create_server(self, tenant_id, group_id, server_id):
        """
        Create a server in Bobby.  This means that Bobby will look up all of the
        policies and add checks and alarms as necessary.

        You need to create the group before you can create a policy or server in it.

        :param tenant_id: The tenant ID of the policy to create in Bobby

        :param group_id: The group ID of the scaling group to create in Bobby

        :param server_id: The Nova server URI to create in Bobby.

        :return: a ``dict`` containing the server object on Bobby's end if successful.
            returns an errorback if the response is not a 201 Created.
        """
        payload = {
            'serverId': server_id,
            'entityId': 'Damnit, Bobby'  # Bobby is going to create the entity ID.
        }
        d = self.treq_client.post(append_segments(self.server_endpoint, tenant_id, 'groups',
                                                  group_id, 'servers'),
                                  data=json.dumps(payload))
        d.addCallback(check_success, [201])
        d.addErrback(wrap_request_error, self.server_endpoint, 'create_server')
        return d.addCallback(self.treq_client.json_content)

    def create_group(self, tenant_id, group_id):
        """
        Create a group in Bobby.  This will create the notification plan and notification
        for Bobby to work against.  Once you've created the group, you can add
        servers or policies.

        :param tenant_id: The tenant ID of the policy to create in Bobby

        :param group_id: The group ID of the scaling group to create in Bobby

        :return: a ``dict`` containing the group object on Bobby's end if successful.
            returns an errorback if the response is not a 201 Created.
        """
        payload = {
            'groupId': group_id,
            'notification': 'Damnit, Bobby',  # these shouldn't be passed to Bobby
            'notificationPlan': 'Damnit, Bobby'
        }
        d = self.treq_client.post(append_segments(self.server_endpoint,
                                                  tenant_id, 'groups'),
                                  data=json.dumps(payload))
        d.addCallback(check_success, [201])
        d.addErrback(wrap_request_error, self.server_endpoint, 'create_group')
        return d.addCallback(self.treq_client.json_content)
