"""
Marshalling for autoscale reponses
"""
from cafe.engine.models.base import AutoMarshallingModel
from autoscale.models.response.group_response import (Active, Server,
                                                      Lbaas, PolicyArgs)
from autoscale.models.servers import Metadata, Links
import json
import re

_NOTFOUND = object()


class ScalingGroup(AutoMarshallingModel):

    """
    Marshalling for scaling group responses
    """

    def __init__(self, **kwargs):
        super(ScalingGroup, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a ScalingGroup based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'group' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['group'])
        return ret

    @classmethod
    def _dict_to_obj(cls, scaling_group_dict):
        """
        Helper method to turn dictionary into Group instance.
        """
        scaling_group = ScalingGroup(**scaling_group_dict)
        if hasattr(scaling_group, 'links'):
            scaling_group.links = Links._dict_to_obj(scaling_group.links)
        if hasattr(scaling_group, 'id'):
            setattr(scaling_group, 'id', getattr(scaling_group, 'id'))
        if hasattr(scaling_group, 'groupConfiguration'):
            scaling_group.groupConfiguration = Group._dict_to_obj(
                scaling_group.groupConfiguration)
        if hasattr(scaling_group, 'state'):
            scaling_group.state = Group._dict_to_obj(scaling_group.state)
        if hasattr(scaling_group, 'launchConfiguration'):
            scaling_group.launchConfiguration = \
                scaling_group.launchConfiguration['args']
            scaling_group.launchConfiguration = Config._dict_to_obj(
                scaling_group.launchConfiguration)
        if hasattr(scaling_group, 'scalingPolicies'):
            temp = []
            for policy in scaling_group.scalingPolicies:
                s = Policy._dict_to_obj(policy)
                temp.append(s)
                setattr(scaling_group, 'scalingPolicies', temp)
        for each in scaling_group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(scaling_group, newkey, scaling_group_dict[each])
        return scaling_group

    def min_details(self):
        """
        @summary: Get the Minimum details of scaling group
        @return: Minimum details of scaling group i.e. id and links
        @rtype: ScalingGroup
        """
        return Group(id=self.id, links=self.links)


class Group(AutoMarshallingModel):

    """
    works for the autoscaling groups configs amd launch configs
    """

    def __init__(self, **kwargs):
        super(Group, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Group based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'groupConfiguration' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['groupConfiguration'])
        if 'group' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['group'])
        return ret

    @classmethod
    def _dict_to_obj(cls, group_dict):
        """
        Helper method to turn dictionary into Group instance.
        """
        group = Group(**group_dict)
        if hasattr(group, 'links'):
            group.links = Links._dict_to_obj(group.links)
        if hasattr(group, 'metadata'):
            group.metadata = Metadata._dict_to_obj(group.metadata)
        if hasattr(group, 'active'):
            group.active = Active._json_to_obj(group.active)
        for each in group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(group, newkey, group_dict[each])
        return group


class Groups(AutoMarshallingModel):

    """
    works for list scaling groups
    """

    def __init__(self, **kwargs):
        super(Groups, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Group based on the json serialized_str
        passed in.
        """
        json_dict = json.loads(serialized_str)
        return cls._dict_to_obj(json_dict)

    @classmethod
    def _dict_to_obj(cls, groups_dict):
        """
        Helper method to turn dictionary into Group instance.
        """
        groups = Groups(**groups_dict)
        if hasattr(groups, 'groups_links'):
            groups.groups_links = Links._dict_to_obj(groups.groups_links)
        if hasattr(groups, 'groups'):
            groups.groups = [Group._dict_to_obj(g) for g in groups.groups]
        return groups


class Config(AutoMarshallingModel):

    """
    works for the autoscaling groups configs amd launch configs
    """

    def __init__(self, **kwargs):
        super(Config, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Config based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'launchConfiguration' in json_dict.keys():
            json_dict = json_dict['launchConfiguration']
            ret = cls._dict_to_obj(json_dict['args'])
        return ret

    @classmethod
    def _dict_to_obj(cls, config_dict):
        """
        Helper method to turn dictionary into Config instance.
        """
        config = Config(**config_dict)
        if hasattr(config, 'server'):
            config.server = Server._json_to_obj(config.server)
        if hasattr(config, 'loadBalancers'):
            config.loadBalancers = Lbaas._json_to_obj(config.loadBalancers)
        for each in config_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(config, newkey, config_dict[each])
        return config


class Policy(AutoMarshallingModel):

    """
    works for the autoscaling policies

     LK NOTE: This class does not support a "policies_links" attribute
     >> handle the singular "policy" case
     ?? WHy would this be called?

    """

    def __init__(self, **kwargs):
        super(Policy, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Policy based on the json
        serialized_str passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'policy' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['policy'])
        if any(['policies' in json_dict.keys(), 'scalingPolicies' in json_dict.keys()]):
            ret = []
            for policy in json_dict['policies']:
                s = cls._dict_to_obj(policy)
                ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, policy_dict):
        """
        Helper method to turn dictionary into Policy instance
        """
        policy = Policy(**policy_dict)
        if hasattr(policy, 'links'):
            policy.links = Links._dict_to_obj(policy.links)
        if hasattr(policy, 'args'):
            policy.args = PolicyArgs._dict_to_obj(policy.args)
        attr_list = ['id', 'name', 'change', 'changePercent',
                     'desiredCapacity', 'cooldown', 'type']
        for k in attr_list:
            if hasattr(policy, k):
                setattr(policy, k, getattr(policy, k))
        for each in policy_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(policy, newkey, policy_dict[each])
        return policy


class Policies(AutoMarshallingModel):
    """
    A marshalling object that works for paginated scaling group policies
    """

    def __init__(self, **kwargs):
        super(Policies, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    # LK NOTE: Where is this called?
    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Return an object with attributes corresponding to the json serialized
        string for paged policy listings
        """

        json_dict = json.loads(serialized_str)
        # use the Policies dict_to_object classmethod to create the object
        return cls._dict_to_obj(json_dict)

    @classmethod
    def _dict_to_obj(cls, policies_dict):
        """
        Helper method to transform a dictionary into a Policies instance
        """

        policies = Policies(**policies_dict)
        if hasattr(policies, 'policies_links'):
            policies.policies_links = Links._dict_to_obj(policies.policies_links)
        if hasattr(policies, 'policies'):
            policies.policies = [
                Policy._dict_to_obj(p) for p in policies.policies]
        return policies


class Webhook(AutoMarshallingModel):

    """
    works for autoscaling policies' webhooks
    @todo: if single webhook is created, will it be webhooks or webhook
    """

    def __init__(self, **kwargs):
        super(Webhook, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Webhook based on the json
        serialized_str passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'webhook' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['webhook'])
        if 'webhooks' in json_dict.keys():
            ret = []
            for webhook in json_dict['webhooks']:
                s = cls._dict_to_obj(webhook)
                ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, webhook_dict):
        """
        Helper method to turn dictionary into Webhook instance
        """
        webhook = Webhook(**webhook_dict)
        if hasattr(webhook, 'links'):
            webhook.links = Links._dict_to_obj(webhook.links)
        if hasattr(webhook, 'metadata'):
            webhook.metadata = Metadata._dict_to_obj(webhook.metadata)
        attr_list = ['id', 'name', 'url']
        for k in attr_list:
            if hasattr(webhook, k):
                setattr(webhook, k, getattr(webhook, k))
        for each in webhook_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(webhook, newkey, webhook_dict[each])
        return webhook
