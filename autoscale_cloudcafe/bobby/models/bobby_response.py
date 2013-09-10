"""
Marshalling for bobby reponses
"""
from cafe.engine.models.base import AutoMarshallingModel
from autoscale.models.servers import Links
import json
import re


class BobbyGroup(AutoMarshallingModel):

    """
    Marshalling objects for Bobby's groups
    """

    def __init__(self, **kwargs):
        super(BobbyGroup, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Bobby Group based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'groups' in json_dict.keys():
            ret = []
            for group in json_dict['groups']:
                s = cls._dict_to_obj(group)
                ret.append(s)
        else:
            ret = cls._dict_to_obj(json_dict)
        return ret

    @classmethod
    def _dict_to_obj(cls, group_dict):
        """
        Helper method to turn dictionary into BobbyGroup instance.
        """
        group = BobbyGroup(**group_dict)
        if hasattr(group, 'links'):
            group.links = Links._dict_to_obj(group.links)
        attr_list = ['groupId', 'notification', 'notificationPlan', 'tenantId']
        for k in attr_list:
            if hasattr(group, k):
                setattr(group, k, getattr(group, k))
        for each in group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(group, newkey, group_dict[each])
        return group


class ServerGroup(AutoMarshallingModel):

    """
    Marshalling objects for Bobby's server group
    """

    def __init__(self, **kwargs):
        super(ServerGroup, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Server Group based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'servers' in json_dict.keys():
            ret = []
            for server_group in json_dict['servers']:
                s = cls._dict_to_obj(server_group)
                ret.append(s)
        else:
            ret = cls._dict_to_obj(json_dict)
        return ret

    @classmethod
    def _dict_to_obj(cls, server_group_dict):
        """
        Helper method to turn dictionary into Server Group instance.
        """
        server_group = ServerGroup(**server_group_dict)
        if hasattr(server_group, 'links'):
            server_group.links = Links._dict_to_obj(server_group.links)
        attr_list = ['groupId', 'entityId', 'serverId']
        for k in attr_list:
            if hasattr(server_group, k):
                setattr(server_group, k, getattr(server_group, k))
        for each in server_group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(server_group, newkey, server_group_dict[each])
        return server_group


class Policies(AutoMarshallingModel):

    """
    Marshalling objects for Bobby's Policies Instance
    """

    def __init__(self, **kwargs):
        super(Policies, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of Bobby Group's policies based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'policies' in json_dict.keys():
            ret = []
            for policies in json_dict['policies']:
                s = cls._dict_to_obj(policies)
                ret.append(s)
        else:
            ret = cls._dict_to_obj(json_dict)
        return ret

    @classmethod
    def _dict_to_obj(cls, policies_dict):
        """
        Method to turn dictionary into Policies instance.
        """
        policies = Policies(**policies_dict)
        if hasattr(policies, 'links'):
            policies.links = Links._dict_to_obj(policies.links)
            attr_list = ['groupId', 'policyId', 'alarmTemplate', 'checkTemplate']
            # the alarmTemplate and checkTemplate above is temporary
        for k in attr_list:
            if hasattr(policies, k):
                setattr(policies, k, getattr(policies, k))
        # if hasattr(policies, 'alarmTemplate'):
        #     policies.alarmTemplate = Alarm._dict_to_obj(policies.alarmTemplate)
        # if hasattr(policies, 'checkTemplate'):
        #     policies.checkTemplate = Check._dict_to_obj(policies.checkTemplate)
        for each in policies_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(policies, newkey, policies_dict[each])
        return policies


class Alarm(AutoMarshallingModel):
    """
    Marshalling objects for Bobby policies' alarms
    """
    def __init__(self, **kwargs):
        super(Alarm, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _dict_to_obj(cls, alarm_dict):
        """
        Method to turn dictionary into Alarm instance.
        """
        alarm = Alarm(**alarm_dict)
        if hasattr(alarm, 'criteria'):
            setattr(alarm, 'criteria', getattr(alarm, 'criteria'))
        return alarm


class Check(AutoMarshallingModel):
    """
    Marshalling objects for Bobby policies' Checks
    """
    def __init__(self, **kwargs):
        super(Check, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _dict_to_obj(cls, check_dict):
        """
        Method to turn dictionary into check instance.
        """
        check = Check(**check_dict)
        if hasattr(check, 'details'):
            check.details = Details._dict_to_obj(check.details)
        for each in check_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(check, newkey, check_dict[each])
        return check


class Details(AutoMarshallingModel):
    """
    Marshalling objects for Bobby policies' Details
    """
    def __init__(self, **kwargs):
        super(Details, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _dict_to_obj(cls, details_dict):
        """
        Method to turn dictionary into details instance.
        """
        details = Details(**details_dict)
        attr_list = ['url', 'method']
        for k in attr_list:
            if hasattr(details, k):
                setattr(details, k, getattr(details, k))
        for each in details_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(details, newkey, details_dict[each])
        return details
