"""
Client objects for all the bobby api calls
"""
from bobby.models.bobby_response import BobbyGroup, ServerGroup, Policies
from bobby.models.bobby_requests import BobbyGroup_Request, ServerGroup_Request, \
    BobbyPolicies_Request
from cafe.engine.clients.rest import AutoMarshallingRestClient


class BobbyAPIClient(AutoMarshallingRestClient):

    """
    Client objects for all bobby api calls
    """

    def __init__(self, url, auth_token, serialize_format=None,
                 deserialize_format=None):
        super(BobbyAPIClient, self).__init__(serialize_format,
                                             deserialize_format)
        self.url = url
        self.auth_token = auth_token
        self.default_headers['X-Auth-Token'] = auth_token
        self.default_headers['Content-Type'] = 'application/%s' % \
                                               self.serialize_format
        self.default_headers['Accept'] = 'application/%s' % \
                                         self.deserialize_format

    def list_groups(self, requestslib_kwargs=None):
        """
        :summary: Lists all groups for a tenant id
        :return: Response Object containing response code 200 and body with
                details of autoscaling groups such as id, links and the
                notification and notification plan for that group
        :rtype: Response Object

        GET
        '{tenant_id}/groups/'
        """

        url = '{0}/groups/'.format(self.url)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=BobbyGroup)

    def create_group(self, group_id, notification, notification_plan,
                     requestslib_kwargs=None):
        """
        :summary: Create a group
        :param group_id: The scaling group id
        :type name: String
        :param notification: The notification for the server group
        :type cooldown: String
        :param notification_plan: The notification plan for the server group
        :type change: String
        :return: Response Object containing response code 201 and body with
                details of newly created group
        :rtype: Response Object

        POST
        '/{tenantId}/groups'
        """
        url = '{0}/groups'.format(self.url)
        group = BobbyGroup_Request(group_id=group_id,
                                   notification=notification,
                                   notification_plan=notification_plan)
        return self.request('POST', url,
                            request_entity=group,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=BobbyGroup)

    def get_group(self, group_id, requestslib_kwargs=None):
        """
        :summary: Get the group with the given group_Id
        :return: Response Object containing response code 200 and body with
                 details of the given group such as its ID, links, notification
                 and notification plan
        :rtype: Response Object

        GET
        '{tenant_id}/groups/{group_id}'
        """
        url = '{0}/groups/{1}'.format(self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=BobbyGroup)

    def delete_group(self, group_id, requestslib_kwargs=None):
        """
        :summary: Deletes the group (when no servers on it ??)
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 204
                 on success and empty body
        :rtype: Response Object

        DELETE
        '/{tenantId}/groups/{groupId}'
        """

        url = '{0}/groups/{1}/'.format(self.url, group_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)

    def list_server_groups(self, group_id, requestslib_kwargs=None):
        """
        :summary: List all the servers for a given group ID.
        :return: Response Object containing response code 200 and body with
                details of server such as entity ID, group ID and links
        :rtype: Response Object

        GET
        '/{tenantId}/groups/{groupId}/servers'
        """

        url = '{0}/groups/{1}/servers'.format(self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=ServerGroup)

    def create_server_group(self, group_id, entity_id, server_id,
                            requestslib_kwargs=None):
        """
        :summary: Create a server group
        :param group_id: The scaling group id
        :type name: String
        :param entity_id: The entity Id for the server in the group
        :type cooldown: String
        :param server_id: The server id of the server in the group
        :type change: String
        :return: Response Object containing response code 201 and body with
                details of newly created server group
        :rtype: Response Object

        POST
        '/{tenantId}/groups/{groupId}/servers'
        """
        url = '{0}/groups/{1}/servers'.format(self.url, group_id)
        server_group = ServerGroup_Request(entity_id=entity_id,
                                           server_id=server_id)
        return self.request('POST', url,
                            request_entity=server_group,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=ServerGroup)

    def get_server_group(self, group_id, server_id, requestslib_kwargs=None):
        """
        :summary: Get the server group with the given group_Id
        :param group_id: The scaling group id
        :type name: String
        :param server_id: The server id of the server in the group
        :type change: String
        :return: Response Object containing response code 200 and body with
                 details of server group
        :rtype: Response Object

        GET
        '/{tenantId}/groups/{groupId}/servers/{serverId}'
        """
        url = '{0}/groups/{1}/servers/{2}'.format(self.url, group_id, server_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=ServerGroup)

    def delete_server_group(self, group_id, server_id, requestslib_kwargs=None):
        """
        :summary: Deletes the server group (when empty ??)
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param server_id: The server id of the server in the group
        :type change: String
        :return: Response Object containing response code 204
                 on success and empty body
        :rtype: Response Object

        DELETE
        '/{tenantId}/groups/{groupId}/servers/{serverId}'
        """

        url = '{0}/groups/{1}/servers/{2}'.format(self.url, group_id, server_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)

    def list_groups_policies(self, group_id, requestslib_kwargs=None):
        """
        :summary: List all the policies for a given group ID.
        :return: Response Object containing response code 200 and body with
                details of the associated policies, such as the alarm template
                and check template
        :rtype: Response Object

        GET
        '/{tenantId}/groups/{groupId}/policies'
        """

        url = '{0}/groups/{1}/policies'.format(self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Policies)

    def create_groups_policies(self, group_id, entity_id, policy_id,
                               alarm_id, check_id,
                               requestslib_kwargs=None):
        """
        :summary: Create a policy object.
        :param group_id: The scaling group id
        :type name: String
        :param entity_id: The entity Id for the server in the group
        :type cooldown: String
        :param policy_id: The server id of the server in the group
        :type change: String
        :return: Response Object containing response code 201 and body with
                details of newly created server group
        :rtype: Response Object

        POST
        '/{tenantId}/groups/{groupId}/policies'
        """
        url = '{0}/groups/{1}/policies'.format(self.url, group_id)
        group_policy = BobbyPolicies_Request(entity_id=entity_id,
                                             policy_id=policy_id,
                                             alarm_id=alarm_id,
                                             check_id=check_id)
        return self.request('POST', url,
                            request_entity=group_policy,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Policies)

    def get_groups_policy(self, group_id, policy_id, requestslib_kwargs=None):
        """
        :summary: Get a policy in the group
        :param group_id: The scaling group id
        :type name: String
        :param policy_id: The policy id of the policy in the group
        :type change: String
        :return: Response Object containing response code 200 and body with
                 details of policy group
        :rtype: Response Object

        GET
        '/{tenantId}/groups/{groupId}/policies/{policyId}'
        """
        url = '{0}/groups/{1}/policies/{2}'.format(self.url, group_id, policy_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Policies)

    def delete_groups_policy(self, group_id, policy_id, requestslib_kwargs=None):
        """
        :summary: Deletes the policy
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param policy_id: The policy id of the policy in the group
        :type change: String
        :return: Response Object containing response code 204
                 on success and empty body
        :rtype: Response Object

        DELETE
        '/{tenantId}/groups/{groupId}/policies/{policyId}'
        """

        url = '{0}/groups/{1}/policies/{2}'.format(self.url, group_id, policy_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)
