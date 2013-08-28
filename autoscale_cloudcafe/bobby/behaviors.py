"""
Behaviors for Bobby
"""
from cafe.engine.behaviors import BaseBehavior
from cloudcafe.common.tools.datagen import rand_name
from cloudcafe.common.resources import ResourcePool


class BobbyBehaviors(BaseBehavior):

    """
    :summary: Behavior Module for the Bobby REST API
    :note: Should be the primary interface to a test case or external tool
    """

    def __init__(self, bobby_config, bobby_client):
        """
        Instantiate config and client
        """
        super(BobbyBehaviors, self).__init__()
        self.bobby_config = bobby_config
        self.bobby_client = bobby_client
        self.resources = ResourcePool()

    def create_bobby_group_given(self, group_id=None, notification=None,
                                 notification_plan=None):
        """
        Creates a bobby group with the given values
        """
        group_id = group_id or rand_name('012345DIFF-78f3-4543-85bc1-')
        notification = notification or self.bobby_config.notification
        notification_plan = notification_plan or self.bobby_config.notification_plan
        bobby_group = self.bobby_client.create_group(
            group_id=group_id,
            notification=notification,
            notification_plan=notification_plan)
        self.resources.add(group_id, self.bobby_client.delete_group)
        return bobby_group.entity

    def create_bobby_server_group_given(self, group_id=None, server_id=None,
                                        entity_id=None):
        """
        Creates a bobby group with the given values
        """
        group_id = group_id or self.bobby_config.group_id
        server_id = server_id or rand_name('0123SERVER-78f3-4543-85bc1-')
        entity_id = entity_id or rand_name('0123ENTITY-78f3-4543-85bc1-')
        bobby_server_group = self.bobby_client.create_server_group(
            group_id=group_id,
            entity_id=entity_id,
            server_id=server_id)
        self.resources.add(group_id, self.bobby_client.delete_group)
        return bobby_server_group

    def create_bobby_policy_given(self, group_id=None, policy_id=None,
                                  alarm_template=None, check_template=None):
        """
        Creates a policy in bobby with the given values
        """
        group_id = group_id or self.bobby_config.group_id
        policy_id = policy_id or rand_name('0123POLICY-78f3-4543-85bc1-')
        check_template = check_template or '7867' or \
            {
                "label": "Website check 1",
                "type": "remote.http",
                "details": {
                    "url": "http://www.foo.com",
                    "method": "GET"
                },
                "monitoring_zones_poll": [
                    "mzA"
                ],
                "timeout": 30,
                "period": 100,
                "target_alias": "default"
            }
        alarm_template = alarm_template or '8787' or \
            {"criteria": "if (metric[\"duration\"] >= 2) { return new AlarmStatus(OK); }"
                " return new AlarmStatus(CRITICAL);"}
        bobby_policy = self.bobby_client.create_bobby_policy(
            group_id=group_id,
            policy_id=policy_id,
            check_template=check_template,
            alarm_template=alarm_template)
        self.resources.add(group_id, self.bobby_client.delete_group)
        return bobby_policy
