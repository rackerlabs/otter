"""
Client objects for all the autoscale api calls
"""
from autoscale.models.response.autoscale_response import Group,\
    Config, Policy, Webhook, ScalingGroup
from autoscale.models.request.autoscale_requests import \
    Group_Request, Policy_Request, Webhook_Request, Config_Request, \
    ScalingGroup_Request, Update_Policy_Request, Update_Webhook_Request
from cafe.engine.clients.rest import AutoMarshallingRestClient
from urlparse import urlparse


class AutoscalingAPIClient(AutoMarshallingRestClient):

    """
    Client objects for all the autoscale api calls
    """

    def __init__(self, url, auth_token, serialize_format=None,
                 deserialize_format=None):
        super(AutoscalingAPIClient, self).__init__(serialize_format,
                                                   deserialize_format)
        self.url = url
        self.auth_token = auth_token
        # self.tenant_id = tenant_id
        self.default_headers['X-Auth-Token'] = auth_token
        self.default_headers['Content-Type'] = 'application/%s' % \
                                               self.serialize_format
        self.default_headers['Accept'] = 'application/%s' % \
                                         self.deserialize_format

    def create_scaling_group(self, gc_name, gc_cooldown, gc_min_entities,
                             lc_name, lc_image_ref, lc_flavor_ref,
                             gc_max_entities=None, gc_metadata=None,
                             lc_personality=None, lc_metadata=None,
                             lc_disk_config=None, lc_networks=None,
                             lc_load_balancers=None, sp_list=None,
                             requestslib_kwargs=None):
        """
        :summary: Create scaling group
        :param gc_name: The name of the scaling group
        :type name: String
        :param gc_cooldown: period before more entities are added in seconds
        :type cooldown: Integer
        :param gc_min_entities: Minimum number of entities in the scaling
                                group
        :type change: Integer
        :param gc_max_entities: Maximum number of entities in the scaling
                                group
        :type change_percent: Integer
        :param gc_metadata: User-provided key-value metadata
        :type gc_metadata: String
        :param lc_name: The name of the server.
        :type lc_name: String
        :param lc_image_ref: The reference to the image used to build the server
        :type lc_image_ref: String
        :param lc_flavor_ref: The flavor used to build the server.
        :type lc_flavor_ref: String
        :param lc_metadata: A dictionary of values to be used as metadata.
        :type lc_metadata: Dictionary. The limit is 5 key/values.
        :param lc_personality: A list of dictionaries for files to be
                              injected into the server.
        :type lc_personality: List
        :param lc_disk_config: MANUAL/AUTO/None
        :type lc_disk_config: String
        :param lc_networks: The network for the server
        :type lc_networks: Numbers
        :param lc_load_balancers: List of the load balancers
        :type lc_loadbalancers: List
        :param sp_list: List of scaling policies
        :type sp_list: List
        :return: Response Object containing response code 201
                 on success and body containg the scaling group
                 details such as group config, launch config and
                 list of scaling policies
        :rtype: Response Object

        POST
        '/{tenantId}/groups'
        """
        url = '%s/groups' % (self.url)
        # Option "core" - Creates rack user only. See servermill build config option
        if lc_metadata:
            lc_metadata['build_config'] = 'core'
        else:
            lc_metadata = dict(build_config='core')
        scaling_group = ScalingGroup_Request(gc_name=gc_name,
                                             gc_cooldown=gc_cooldown,
                                             gc_min_entities=gc_min_entities,
                                             gc_max_entities=gc_max_entities,
                                             gc_metadata=gc_metadata,
                                             lc_name=lc_name,
                                             lc_image_ref=lc_image_ref,
                                             lc_flavor_ref=lc_flavor_ref,
                                             lc_personality=lc_personality,
                                             lc_metadata=lc_metadata,
                                             lc_disk_config=lc_disk_config,
                                             lc_networks=lc_networks,
                                             lc_load_balancers=lc_load_balancers,
                                             sp_list=sp_list)
        return self.request('POST', url,
                            request_entity=scaling_group,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=ScalingGroup)

    def list_scaling_groups(self, requestslib_kwargs=None):
        """
        :summary: Lists IDs and links for all scaling groups
        :return: Response Object containing response code 200 and body with
                details of autoscaling groups such as id and links
        :rtype: Response Object

        GET
        {tenant_id}/groups/
        """

        url = '%s/groups/' % (self.url)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Group)

    def view_manifest_config_for_scaling_group(self, group_id,
                                               requestslib_kwargs=None):
        """
        :summary: List full details of scaling configuration, including launch
                  configs and scaling policies
        :return: Response Object containing response code 200 and body with
                 details of autoscaling group such as launch config, group
                 config and scaling policies
        :rtype: Response Object

        GET
        {tenant_id}/groups/{group_id}
        """

        self.group_id = group_id
        url_new = str(group_id)
        url_scheme = urlparse(url_new).scheme
        url = url_new if url_scheme else '%s/groups/%s' % (self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=ScalingGroup)

    def pause_scaling_group(self, group_id, requestslib_kwargs=None):
        """
        :summary: Pause a scaling group. (no scaling policies will be executed)
        :return: Response object containing the response code 204 on success
                  and empty body
        :rtype: Response Object

        POST
        /{tenantId}/groups/{groupId}/pause/
        """
        self.group_id = group_id
        url = '%s/groups/%s/pause/' % (self.url, self.group_id)
        return self.request('POST', url,
                            requestslib_kwargs=requestslib_kwargs)

    def resume_scaling_group(self, group_id, requestslib_kwargs=None):
        """
        :summary: Resume a scaling group. (scaling policies will continue to execute)
        :return: Response object containing the response code 204 on success
                  and empty body
        :rtype: Response Object

        POST
        /{tenantId}/groups/{groupId}/resume/
        """
        self.group_id = group_id
        url = '%s/groups/%s/resume/' % (self.url, self.group_id)
        return self.request('POST', url,
                            requestslib_kwargs=requestslib_kwargs)

    def delete_scaling_group(self, group_id, requestslib_kwargs=None):
        """
        :summary: Deletes the scaling group when empty. Rejects when group
                  has entities.
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 204
                 on success and empty body
        :rtype: Response Object

            DELETE
            '/{tenantId}/groups/{groupId}'
        """

        self.group_id = group_id
        url = '%s/groups/%s/' % (self.url, self.group_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)

    def list_status_entities_sgroups(self, group_id, requestslib_kwargs=None):
        """
        :summary: List status of entities in autoscaling group
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 200 and body
                 with current state of the group including list of active
                 & pending entities and desired capacity number of servers
        :rtype: Response Object

            GET
            '/{tenantId}/groups/{groupId}'/state'
        """
        self.group_id = group_id
        url = '%s/groups/%s/state/' % (self.url, self.group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Group)

    def view_scaling_group_config(self, group_id, requestslib_kwargs=None):
        """
        :summary: List scaling group configuration details
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 200 and body with the
                 attributes of the group_config
        :rtype: Response Object
         GET
         '/<string:tenantId>/groups/<string:groupId>/config'
        """
        # self.group_id = group_id

        url = '%s/groups/%s/config/' % (self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Group)

    def update_group_config(self, group_id, name, cooldown, min_entities,
                            max_entities=None, metadata=None,
                            requestslib_kwargs=None):
        """
        :summary: Update/Create scaling group configuration details
        :param name: The name of the scaling group
        :type name: String
        :param cooldown: The cooldown time for the scaling group
        :type cooldown: Number
        :param min_entities: Minimum number of entities in the scaling group
        :type min_entities: Integer
        :param max_entities: Maximum number of entities in the scaling group
        :type max_entities: Integer or null
        :param metadata: User-provided key-value metadata
        :type metadata: object
        :return: Response Object containing response code 204
                 on success and empty body
        :rtype: Response Object

        PUT
        '/<string:tenantId>/groups/<string:groupId>/config'
        """
        url = '%s/groups/%s/config/' % (self.url, group_id)
        group = Group_Request(name=name, cooldown=cooldown,
                              min_entities=min_entities,
                              max_entities=max_entities,
                              metadata=metadata)
        return self.request('PUT', url,
                            request_entity=group,
                            requestslib_kwargs=requestslib_kwargs)

    def view_launch_config(self, group_id, requestslib_kwargs=None):
        """
        :summary: List the scaling group's launch configuration
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 200 and body
                 with the attributes of the launch config such as the
                 server and loadbalancer configs
        :rtype: Response Object

        GET
        '/<string:tenantId>/groups/<string:groupId>/launch'
        """
        url = '%s/groups/%s/launch/' % (self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Config)

    def update_launch_config(self, group_id, name, image_ref, flavor_ref,
                             personality=None, metadata=None,
                             disk_config=None, networks=None,
                             load_balancers=None,
                             requestslib_kwargs=None):
        """
        :summary: Update/Create launch configuration
        :return: Response Object containing response code 204
         on success and empty body
        :rtype: Response Object

            PUT
            '/<string:tenantId>/groups/<string:groupId>/launch'
        """
        url = '%s/groups/%s/launch/' % (self.url, group_id)
        config = Config_Request(name=name, image_ref=image_ref,
                                flavor_ref=flavor_ref,
                                personality=personality, metadata=metadata,
                                disk_config=disk_config, networks=networks,
                                load_balancers=load_balancers)
        return self.request('PUT', url,
                            request_entity=config,
                            requestslib_kwargs=requestslib_kwargs)

    def create_policy(self, group_id, name, cooldown,
                      change=None, change_percent=None,
                      desired_capacity=None, policy_type=None,
                      args=None, requestslib_kwargs=None):
        """
        :summary: Create scaling policy
        :param name: A unique name for the scaling policy
        :type name: String
        :param cooldown: The cooldown time for the policy
        :type cooldown: Number
        :param change: The change to make in the number of servers in the
                      scaling group (non-zero)
        :type change: Integer
        :param change_percent: The changepercent to make in the number of
                              servers in the scaling group
        :type change_percent: Number
        :param desired_capacity: The desired capacity is the no of servers to be
                            in the scaling group
        :type desired_capacity: Integer
        :param policy_type: What type of policy this is
        :type policy_type: String
        :return: Response Object containing response code 201
         on success and empty body
        :rtype: Response Object

        POST
        '/{tenantId}/groups/{groupId}/policy'
        """
        url = '%s/groups/%s/policies/' % (self.url, group_id)
        policy = Policy_Request(name=name, cooldown=cooldown, change=change,
                                change_percent=change_percent,
                                desired_capacity=desired_capacity,
                                policy_type=policy_type, args=args)
        return self.request('POST', url,
                            response_entity_type=Policy,
                            request_entity=policy,
                            requestslib_kwargs=requestslib_kwargs)

    def list_policies(self, group_id, requestslib_kwargs=None):
        """
        :summary: List the scaling group's policy configurations
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :return: Response Object containing response code 200 and body with
                 the list of the policy configs
        :rtype: Response Object

        GET
        '/<string:tenantId>/groups/<string:groupId>/policy'
        """
        url = '%s/groups/%s/policies/' % (self.url, group_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Policy)

    def update_policy(self, group_id, policy_id, name, cooldown, change=None,
                      change_percent=None, desired_capacity=None,
                      policy_type=None, args=None, requestslib_kwargs=None):
        """
        :summary: Update/Create details of a specific scaling policy
        :param name: The name of the policy
        :type name: String
        :param cooldown: The cooldown time for the policy
        :type cooldown: Number
        :param policy_type: What type of policy this is
        :type policy_type: String
        :return: Response Object containing response code 204
         on success and empty body
        :rtype: Response Object

            PUT
            '/<string:tenantId>/groups/<groupId>/policy/<policyId>'
        """
        url = '%s/groups/%s/policies/%s/' % (self.url, group_id, policy_id)
        policy = Update_Policy_Request(
            name=name, cooldown=cooldown, change=change,
            change_percent=change_percent,
            desired_capacity=desired_capacity,
            policy_type=policy_type,
            args=args)
        return self.request('PUT', url,
                            request_entity=policy,
                            requestslib_kwargs=requestslib_kwargs)

    def get_policy_details(self, group_id, policy_id, requestslib_kwargs=None):
        """
        :summary: Get details of a specific scaling policy
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param policy_id: The id of an existing scaling policy.
        :type policy_id: String
        :return: Response Object containing response code 200 and body with
                 the attributes of the given policy
        :rtype: Response Object

        GET
        '/<string:tenantId>/groups/<string:groupId>/policy/<string:policyId>'
        """
        self.policy_id = policy_id
        url_new = str(policy_id)
        url_scheme = urlparse(url_new).scheme
        url = url_new if url_scheme else '%s/groups/%s/policies/%s/' % (
            self.url, group_id, policy_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Policy)

    def delete_scaling_policy(self, group_id, policy_id,
                              requestslib_kwargs=None):
        """
        :summary: Delete a specific scaling policy
        :param group_id: The id of an existing scaling group.
        :type group_id: String
         :param policy_id: The id of an existing scaling group policy.
        :type policy_id: String
        :return: Response Object containing response code 204
         on success and empty body
        :rtype: Response Object

            DELETE
            '/{tenantId}/groups/{groupId}/policy/{policyId}'
        """
        url = '%s/groups/%s/policies/%s/' % (self.url, group_id, policy_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)

    def execute_policy(self, group_id, policy_id,
                       requestslib_kwargs=None):
        """
        :summary: Execute a policy
        :param group_id: The id of an existing scaling group.
        :type group_id: String
         :param policy_id: The id of an existing scaling policy.
        :type policy_id: String
        :return: Response Object containing response code 202
         on success and empty body
        :rtype: Response Object

        POST
        '/{tenantId}/groups/{groupId}/policy/{policyId}/execute'
        """
        url = '%s/groups/%s/policies/%s/execute' % (
            self.url, group_id, policy_id)
        return self.request('POST', url,
                            requestslib_kwargs=requestslib_kwargs)

    def create_webhook(self, group_id, policy_id, name, metadata=None,
                       requestslib_kwargs=None):
        """
        :summary: Create a new public webhook for Scaling Policy
        :param name: The name of the webhook
        :type name: String
        :param metadata: The metadata for the webhook
        :type cooldown: dict
        :return: Response Object containing response code 201
         on success and empty body
        :rtype: Response Object

            POST
            '/{tenantId}/groups/{groupId}/policy/{policyId}/webhooks/'
        """
        url = '%s/groups/%s/policies/%s/webhooks/' % (self.url, group_id,
                                                      policy_id)
        webhooks = Webhook_Request(name=name, metadata=metadata)
        return self.request('POST', url,
                            response_entity_type=Webhook,
                            request_entity=webhooks,
                            requestslib_kwargs=requestslib_kwargs)

    def list_webhooks(self, group_id, policy_id, requestslib_kwargs=None):
        """
        :summary: List basic info for all webhooks under scaling policy
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param policy_id: The id of an existing scaling group policy.
        :type policy_id: String
        :return: Response Object containing response code 200 and body with
                 the list of the webhooks for the given policy
        :rtype: Response Object

        GET
        '/<tenantId>/groups/<groupId>/policy/<policyId>/webhook'
        """
        url = '%s/groups/%s/policies/%s/webhooks/' % (
            self.url, group_id, policy_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Webhook)

    def update_webhook(self, group_id, policy_id, webhook_id, name,
                       metadata=None, requestslib_kwargs=None):
        """
        :summary: Update webhook under scaling policy
                  (TBD: Update all webhooks on a policy???)
        :param name: The name of the webhook
        :type name: String
        :param cooldown: The cooldown time for the webhook
        :type cooldown: Integer
        :param URL: The URL of the webhook
        :type URL: String
        :return: Response Object containing response code 204
         on success and empty body
        :rtype: Response Object

        PUT
        '/{tenantId}/groups/{groupId}/policy/{policyId}/webhook/{webhookId}'
        """
        url = '%s/groups/%s/policies/%s/webhooks/%s/' % (self.url, group_id,
                                                         policy_id,
                                                         webhook_id)
        webhook = Update_Webhook_Request(name=name, metadata=metadata)
        return self.request('PUT', url,
                            request_entity=webhook,
                            requestslib_kwargs=requestslib_kwargs)

    def get_webhook(self, group_id, policy_id, webhook_id,
                    requestslib_kwargs=None):
        """
        :summary: Get details of a specific webhook (name, URL, access details)
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param policy_id: The id of an existing scaling group policy.
        :type policy_id: String
        :param webhook_id: The id of an existing scaling webhook.
        :type webhook_id: String
        :return: Response Object containing response code 200 and body with the
                 attributes of the given webhook
        :rtype: Response Object

        GET
        '/<string:tenantId>/groups/<string:groupId>/webhook/<string:webhookId>'
        """
        self.webhook_id = webhook_id
        url_new = str(webhook_id)
        url_scheme = urlparse(url_new).scheme
        url = url_new if url_scheme else '%s/groups/%s/policies/%s/webhooks/%s/' % (
            self.url,
            group_id,
            policy_id,
            webhook_id)
        return self.request('GET', url,
                            requestslib_kwargs=requestslib_kwargs,
                            response_entity_type=Webhook)

    def delete_webhook(self, group_id, policy_id, webhook_id,
                       requestslib_kwargs=None):
        """
        :summary: Delete a public webhook
        :param group_id: The id of an existing scaling group.
        :type group_id: String
        :param policy_id: The id of an existing scaling group policy.
        :type policy_id: String
        :param webhook_id: The id of an existing webhook.
        :type webhook_id: String
        :return: Response Object containing response code 204
         on success and empty body
        :rtype: Response Object

        DELETE
        '/{tenantId}/groups/{groupId}/policy/{policy_id}/webhook/{webhookId}'
        """
        url = '%s/groups/%s/policies/%s/webhooks/%s/' % (self.url, group_id,
                                                         policy_id,
                                                         webhook_id)
        return self.request('DELETE', url,
                            requestslib_kwargs=requestslib_kwargs)

    def execute_webhook(self, webhook_url,
                        requestslib_kwargs=None):
        """
        :summary: Execute a webhook
        :param webhook_url: The capability url generated when a webhook is created
        :return: Response Object containing response code 202
         on success and empty body
        :rtype: Response Object

        POST
        '/execute/<string:capability_version>/<string:capability_hash>/'
        """
        url = webhook_url
        return self.request('POST', url,
                            requestslib_kwargs=requestslib_kwargs)
