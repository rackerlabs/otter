"""
Behaviors for Autoscale
"""
import time
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta


from cafe.engine.behaviors import BaseBehavior
from cloudcafe.common.tools.datagen import rand_name
from autoscale.models.servers import Metadata
from cloudcafe.compute.common.exceptions import TimeoutException, BuildErrorException


class AutoscaleBehaviors(BaseBehavior):

    """
    :summary: Behavior Module for the Autoscale REST API
    :note: Should be the primary interface to a test case or external tool
    """

    def __init__(self, autoscale_config, autoscale_client):
        """
        Instantiate config and client
        """
        super(AutoscaleBehaviors, self).__init__()
        self.autoscale_config = autoscale_config
        self.autoscale_client = autoscale_client

    def create_scaling_group_min(self, gc_name=None,
                                 gc_cooldown=None,
                                 gc_min_entities=None,
                                 lc_name=None,
                                 lc_image_ref=None,
                                 lc_flavor_ref=None):
        """
        Creates a scaling group with only the required fields
        """
        gc_name = gc_name and str(gc_name) or rand_name('test_sgroup')
        if gc_cooldown is None:
            gc_cooldown = int(self.autoscale_config.gc_cooldown)
        if gc_min_entities is None:
            gc_min_entities = int(self.autoscale_config.gc_min_entities)
        lc_name = lc_name and str(lc_name) or rand_name('test_min_srv')
        if lc_image_ref is None:
            lc_image_ref = self.autoscale_config.lc_image_ref
        if lc_flavor_ref is None:
            lc_flavor_ref = self.autoscale_config.lc_flavor_ref
        create_response = self.autoscale_client.create_scaling_group(
            gc_name,
            gc_cooldown,
            gc_min_entities,
            lc_name,
            lc_image_ref,
            lc_flavor_ref)
        return create_response

    def create_scaling_group_given(self, gc_name=None, gc_cooldown=None,
                                   gc_min_entities=None, gc_max_entities=None,
                                   gc_metadata=None, lc_name=None,
                                   lc_image_ref=None, lc_flavor_ref=None,
                                   lc_personality=None, lc_metadata=None,
                                   lc_disk_config=None, lc_networks=None,
                                   lc_load_balancers=None, sp_list=None):
        """
        Creates a scaling group with given parameters and default the other
        required fields if not already given
        """
        gc_name = gc_name and str(gc_name) or rand_name('test_sgroup_bhv_')
        if gc_cooldown is None:
            gc_cooldown = int(self.autoscale_config.gc_cooldown)
        if gc_min_entities is None:
            gc_min_entities = int(self.autoscale_config.gc_min_entities)
        lc_name = lc_name and str(lc_name) or rand_name('test_sg_bhv_srv')
        if lc_image_ref is None:
            lc_image_ref = self.autoscale_config.lc_image_ref
        if lc_flavor_ref is None:
            lc_flavor_ref = self.autoscale_config.lc_flavor_ref
        create_response = self.autoscale_client.create_scaling_group(
            gc_name,
            gc_cooldown,
            gc_min_entities,
            lc_name,
            lc_image_ref,
            lc_flavor_ref,
            gc_max_entities=gc_max_entities,
            gc_metadata=gc_metadata,
            lc_personality=lc_personality,
            lc_metadata=lc_metadata,
            lc_disk_config=lc_disk_config,
            lc_networks=lc_networks,
            lc_load_balancers=lc_load_balancers,
            sp_list=sp_list)
        return create_response

    def wait_for_expected_number_of_active_servers(
        self, group_id, expected_servers,
            interval_time=None, timeout=None):
        """
        :summary: verify the desired capacity in group state is equal to expected servers
         and waits for the specified number of servers to be active on a group
        :param group_id: Group id
        :param expected_servers: Total active servers expected on the group
        :param interval_time: Time to wait during polling group state
        :param timeout: Time to wait before exiting this function
        :return: returns the list of active servers in the group
        """
        interval_time = interval_time or int(
            self.autoscale_config.interval_time)
        timeout = timeout or int(self.autoscale_config.timeout)
        end_time = time.time() + timeout

        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group_id)
        group_state = group_state_response.entity
        if group_state.desiredCapacity != expected_servers:
            raise BuildErrorException(
                'Group %s should have %s servers, but is trying to build %s servers'
                % (group_id, expected_servers, group_state.desiredCapacity))
        while time.time() < end_time:
            resp = self.autoscale_client.list_status_entities_sgroups(group_id)
            group_state = resp.entity
            active_list = group_state.active

            if (group_state.activeCapacity + group_state.pendingCapacity) == 0:
                raise BuildErrorException(
                    'Group Id %s failed to attempt server creation. Group has no servers'
                    % group_id)

            if len(active_list) == expected_servers:
                return [server.id for server in active_list]
            time.sleep(interval_time)
            print "waiting for servers to be active..."

            if group_state.desiredCapacity != expected_servers:
                raise BuildErrorException(
                    'Group %s should have %s servers, but has reduced the build %s servers'
                    % (group_id, expected_servers, group_state.desiredCapacity))
        else:
            raise TimeoutException(
                "wait_for_active_list_in_group_state ran for {0} seconds for group {1} and did not "
                "observe the active server list achieving the expected servers count: {2}.".format(
                    timeout, group_id, expected_servers))

    def create_policy_min(self, group_id, sp_name=None, sp_cooldown=None,
                          sp_change=None, sp_change_percent=None,
                          sp_desired_capacity=None, sp_policy_type=None):
        """
        :summary: creates the policy with change set to default config value
        :params: group_id
        :return: returns the newly created policy in the form of a dict
        :rtype: returns the policy dict
        """
        sp_name = sp_name and str(sp_name) or rand_name('test_sp')
        if sp_cooldown is None:
            sp_cooldown = int(self.autoscale_config.sp_cooldown)
        if sp_policy_type is None:
            sp_policy_type = self.autoscale_config.sp_policy_type
        sp_change = int(self.autoscale_config.sp_change)
        create_response = self.autoscale_client.create_policy(
            group_id=group_id,
            name=sp_name, cooldown=sp_cooldown,
            change=sp_change, policy_type=sp_policy_type)
        policy = AutoscaleBehaviors.get_policy_properties(
            self, create_response.entity)
        return policy

    def create_policy_given(self, group_id, sp_name=None, sp_cooldown=None,
                            sp_change=None, sp_change_percent=None,
                            sp_desired_capacity=None, sp_policy_type=None):
        """
        :summary: creates the specified policy for the given change type
        :params: group_id
        :return: returns the newly created policy object with change set
                 to config's default
        :rtype: returns the policy object
        """
        sp_name = sp_name and str(sp_name) or rand_name('testsp_')
        if sp_cooldown is None:
            sp_cooldown = int(self.autoscale_config.sp_cooldown)
        if sp_policy_type is None:
            sp_policy_type = self.autoscale_config.sp_policy_type
        if sp_change is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                change=sp_change, policy_type=sp_policy_type)
        elif sp_change_percent is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                change_percent=sp_change_percent, policy_type=sp_policy_type)
        elif sp_desired_capacity is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                desired_capacity=sp_desired_capacity, policy_type=sp_policy_type)
        policy = AutoscaleBehaviors.get_policy_properties(
            self, create_response.entity)
        return policy

    def create_schedule_policy_given(
        self, group_id, sp_name=None, sp_cooldown=None,
        sp_change=None, sp_change_percent=None,
        sp_desired_capacity=None, sp_policy_type='schedule',
            schedule_at=None, schedule_cron=None):
        """
        :summary: creates the specified policy for the given schedule
        :return: returns the newly created policy object
        :rtype: returns the policy object
        """
        sp_name = sp_name and str(sp_name) or rand_name('testscheduler_')
        if sp_cooldown is None:
            sp_cooldown = int(self.autoscale_config.sp_cooldown)
        if schedule_cron:
            args = {'cron': schedule_cron}
        elif schedule_at:
            args = {'at': schedule_at}
        else:
            args = {'at': AutoscaleBehaviors.get_time_in_utc(self, 5)}
        if sp_change is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                change=sp_change, policy_type=sp_policy_type, args=args)
        elif sp_change_percent is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                change_percent=sp_change_percent, policy_type=sp_policy_type, args=args)
        elif sp_desired_capacity is not None:
            create_response = self.autoscale_client.create_policy(
                group_id=group_id,
                name=sp_name, cooldown=sp_cooldown,
                desired_capacity=sp_desired_capacity, policy_type=sp_policy_type, args=args)
        if create_response.status_code != 201:
            return dict(status_code=create_response.status_code)
        else:
            policy = AutoscaleBehaviors.get_policy_properties(
                self, policy_list=create_response.entity, status_code=create_response.status_code,
                headers=create_response.headers)
            return policy

    def get_time_in_utc(self, delay):
        """
        Given the delay in seconds, returns current time in utc + the delay
        """
        time_format = '%Y-%m-%dT%H:%M:%S.%fZ'
        return ((datetime.utcnow() + timedelta(seconds=delay)).strftime(time_format))

    def create_policy_webhook(self, group_id, policy_data,
                              execute_webhook=None, execute_policy=None):
        """
        :summary: wrapper for create_policy_given. Given a dict with
                  change type, the change number, cooldown(optional),
                  sets the parameters in create_policy_min and
                  creates a webhook for the policy
        :param: group id
        :param: dict of policy details such as change type,
                change integer/number, cooldown(optional)
                Eg: {'change_percent': 100, 'cooldown': 200}
        :param: execute_webhook. Executes the newly created webhook
        :param: execute_policy. Executes the newly created policy
        :return: dict containing policy id and its webhook id and
                 capability url
        :rtype: dict
        """
        sp_change = sp_change_percent = sp_desired_capacity = sp_cooldown = None
        response_code = None
        if policy_data.get('change_percent'):
            sp_change_percent = policy_data['change_percent']
        if policy_data.get('change'):
            sp_change = policy_data['change']
        if policy_data.get('desired_capacity'):
            sp_desired_capacity = policy_data['desired_capacity']
        if policy_data.get('cooldown'):
            sp_cooldown = policy_data['cooldown']
        policy = AutoscaleBehaviors.create_policy_given(
            self, group_id=group_id, sp_cooldown=sp_cooldown,
            sp_change=sp_change, sp_change_percent=sp_change_percent,
            sp_desired_capacity=sp_desired_capacity)
        wb_name = rand_name('test_wb_')
        create_webhook = self.autoscale_client.create_webhook(
            group_id=group_id,
            policy_id=policy['id'],
            name=wb_name)
        webhook = AutoscaleBehaviors.get_webhooks_properties(
            self, create_webhook.entity)
        if execute_webhook is True:
            execute_webhook_response = self.autoscale_client.execute_webhook(
                webhook['links'].capability)
            response_code = execute_webhook_response.status_code
        if execute_policy is True:
            execute_policy_response = self.autoscale_client.execute_policy(
                group_id=group_id,
                policy_id=policy['id'])
            response_code = execute_policy_response.status_code
        rdata = dict(policy_id=policy['id'], webhook_id=webhook['id'],
                     webhook_url=webhook['links'].capability, execute_response=response_code)
        return rdata

    def calculate_servers(self, current, percentage):
        """
        Given the current number of servers and change percentage,
        returns the servers expected for the percentage.
        """
        return int((current * (Decimal(percentage) / 100)).to_integral_value(ROUND_HALF_UP)) + current

    def to_data(self, data):
        """converts metadata obj to type dict"""
        if 'Metadata' in str(type(data)):
            return Metadata._obj_to_dict(data)

    def network_uuid_list(self, data):
        """converts data into a list"""
        network_list = []
        for i in data:
            if isinstance(i, dict):
                network_list.append(i['uuid'])
            else:
                network_list.append(i.uuid)
        return network_list

    def lbaas_list(self, data):
        """returns lbaas list"""
        lbaas_id_list = []
        lbaas_port_list = []
        for i in data:
            if isinstance(i, dict):
                lbaas_id_list.append(i['loadBalancerId'])
                lbaas_port_list.append(i['port'])
            else:
                lbaas_id_list.append(i.loadBalancerId)
                lbaas_port_list.append(i.port)
        return lbaas_id_list, lbaas_port_list

    def personality_list(self, data):
        """returns personality list"""
        path_list = []
        contents_list = []
        for i in data:
            if isinstance(i, dict):
                path_list.append(i['path'])
                contents_list.append(i['contents'])
            else:
                path_list.append(i.path)
                contents_list.append(i.contents)
        return path_list, contents_list

    def policy_details_list(self, data):
        """returns policy details list"""
        # :todo : make the obj list work for changePercent and desiredCapacity
        policy_name = []
        policy_chng = []
        policy_cooldown = []
        for i in data:
            if isinstance(i, dict):
                chng_type = i.get('change') or i.get(
                    'changePercent') or i.get('desiredCapacity')
                policy_name.append(i['name'])
                policy_chng.append(chng_type)
                policy_cooldown.append(i['cooldown'])
            else:
                policy_name.append(i.name)
                policy_cooldown.append(i.cooldown)
                policy_chng.append(i.change)
        return policy_name, policy_cooldown, policy_chng

    def get_policy_properties(self, policy_list, status_code=None,
                              headers=None):
        """converts policy list object to a dict"""
        # :todo : find the change type
        policy = {}
        for policy_type in policy_list:
            try:
                if policy_type.change:
                    policy['change'] = policy_type.change
            except AttributeError:
                pass
            try:
                if policy_type.changePercent:
                    policy['change_percent'] = policy_type.changePercent
            except AttributeError:
                pass
            try:
                if policy_type.desiredCapacity:
                    policy['desired_capacity'] = policy_type.desiredCapacity
            except AttributeError:
                pass
            try:
                if policy_type.args:
                    try:
                        if policy_type.args.at:
                            policy['schedule_type'] = 'at'
                            policy['schedule_value'] = policy_type.args.at
                    except AttributeError:
                        pass
                    try:
                        if policy_type.args.cron:
                            policy['schedule_type'] = 'cron'
                            policy['schedule_value'] = policy_type.args.cron
                    except AttributeError:
                        pass
            except AttributeError:
                pass

            policy['id'] = policy_type.id
            policy['links'] = policy_type.links
            policy['name'] = policy_type.name
            policy['cooldown'] = policy_type.cooldown
            policy['type'] = policy_type.type
            policy['count'] = len(policy_list)
            policy['status_code'] = status_code
            policy['headers'] = headers
            return policy

    def get_webhooks_properties(self, webhook_list):
        """converts webhook list object to a dict"""
        webhook = {}
        for i in webhook_list:
            webhook['id'] = i.id
            webhook['links'] = i.links
            webhook['name'] = i.name
            try:
                if i.metadata:
                    webhook['metadata'] = i.metadata
            except AttributeError:
                pass
            webhook['count'] = len(webhook_list)
            return webhook
