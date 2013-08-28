"""
Marshalling for autoscale requests
"""
from cafe.engine.models.base import AutoMarshallingModel
import json


class BobbyGroup_Request(AutoMarshallingModel):

    """
    Marshalling for create group requests in bobby
    """

    def __init__(self, group_id, notification,
                 notification_plan):
        super(BobbyGroup_Request, self).__init__()
        self.groupId = group_id
        self.notification = notification
        self.notificationPlan = notification_plan

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class ServerGroup_Request(AutoMarshallingModel):

    """
    Marshalling for create server group requests
    """

    def __init__(self, entity_id, server_id):
        super(ServerGroup_Request, self).__init__()
        self.entityId = entity_id
        self.serverId = server_id

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class BobbyPolicies_Request(AutoMarshallingModel):

    """
    Marshalling for group's create policy requests
    """

    def __init__(self, policy_id, alarm_template,
                 check_template):
        super(BobbyPolicies_Request, self).__init__()
        self.policyId = policy_id
        self.alarmTemplate = alarm_template
        self.checkTemplate = check_template

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class Update_BobbyPolicies_Request(AutoMarshallingModel):

    """
    Marshalling for group's create policy requests
    """

    def __init__(self, alarm_template, check_template):
        super(Update_BobbyPolicies_Request, self).__init__()
        self.alarmTemplate = alarm_template
        self.checkTemplate = check_template

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())
