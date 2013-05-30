"""
Marshalling for autoscale requests
"""
from cafe.engine.models.base import AutoMarshallingModel
from cloudcafe.compute.servers_api.models.requests import CreateServer
import json


class Webhook_Request(AutoMarshallingModel):
    """
    Marshalling for webhook requests
    """

    def __init__(self, name, metadata):
        super(Webhook_Request, self).__init__()
        self.name = name
        #self.url = url
        self.metadata = metadata

    def _obj_to_json(self):
        req = []
        req.append(self._auto_to_dict())
        return json.dumps(req)


class Update_Webhook_Request(AutoMarshallingModel):
    """
    Marshalling for update webhook requests
    """

    def __init__(self, name, metadata):
        super(Update_Webhook_Request, self).__init__()
        self.name = name
        #self.url = url
        self.metadata = metadata

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class Policy_Request(AutoMarshallingModel):
    """
    Marshalling for policy requests
    """

    def __init__(self, name, cooldown, change=None, change_percent=None,
                 desired_capacity=None, policy_type=None):
        super(Policy_Request, self).__init__()
        self.name = name
        self.cooldown = cooldown
        self.change = change
        self.changePercent = change_percent
        self.desiredCapacity = desired_capacity
        self.type = policy_type

    def _obj_to_json(self):
        req = []
        req.append(self._auto_to_dict())
        return json.dumps(req)


class Update_Policy_Request(AutoMarshallingModel):
    """
    Marshalling for update policy requests
    """

    def __init__(self, name, cooldown, change=None, change_percent=None,
                 desired_capacity=None, policy_type=None):
        super(Update_Policy_Request, self).__init__()
        self.name = name
        self.cooldown = cooldown
        self.change = change
        self.changePercent = change_percent
        self.desiredCapacity = desired_capacity
        self.type = policy_type

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class Group_Request(AutoMarshallingModel):
    """
    Marshalling for group requests
    """

    def __init__(self, name, cooldown, min_entities, max_entities=None,
                 metadata=None):
        super(Group_Request, self).__init__()
        self.name = name
        self.cooldown = cooldown
        self.minEntities = min_entities
        self.maxEntities = max_entities
        self.metadata = metadata

    def _obj_to_json(self):
        return json.dumps(self._auto_to_dict())


class Config_Request(AutoMarshallingModel):
    """
    Marshalling for group config requests
    """

    def __init__(self, name, image_ref, flavor_ref, personality=None,
                 metadata=None, disk_config=None, networks=None,
                 load_balancers=None):
        super(Config_Request, self).__init__()
        self.name = name
        self.image_ref = image_ref
        self.flavor_ref = flavor_ref
        self.personality = personality
        self.metadata = metadata
        self.disk_config = disk_config
        self.networks = networks
        self.load_balancers = load_balancers

    def _obj_to_json(self):
        server = CreateServer(name=self.name, imageRef=self.image_ref,
                              flavorRef=self.flavor_ref,
                              personality=self.personality,
                              metadata=self.metadata,
                              diskConfig=self.disk_config,
                              networks=self.networks)
        server_json = server._obj_to_json()
        body = {'type': 'launch_server',
                'args': json.loads(server_json)}
        if self.load_balancers:
            body['args']['loadBalancers'] = self.load_balancers
        #if self.disk_config:
        #    del body['args']['server']['diskConfig']
        return json.dumps(body)


class ScalingGroup_Request(AutoMarshallingModel):
    """
    Marshalling for scaling group requests
    """

    def __init__(self, gc_name, gc_cooldown, gc_min_entities, lc_name,
                 lc_image_ref, lc_flavor_ref,
                 gc_max_entities=None, gc_metadata=None,
                 lc_personality=None, lc_metadata=None,
                 lc_disk_config=None, lc_networks=None,
                 lc_load_balancers=None, sp_list=None):
        super(ScalingGroup_Request, self).__init__()
        self.gc_name = gc_name
        self.gc_cooldown = gc_cooldown
        self.gc_min_entities = gc_min_entities
        self.gc_max_entities = gc_max_entities
        self.gc_metadata = gc_metadata
        self.lc_name = lc_name
        self.lc_image_ref = lc_image_ref
        self.lc_flavor_ref = lc_flavor_ref
        self.lc_personality = lc_personality
        self.lc_metadata = lc_metadata
        self.lc_disk_config = lc_disk_config
        self.lc_networks = lc_networks
        self.lc_load_balancers = lc_load_balancers
        self.sp_list = sp_list

    def _obj_to_json(self):
        config = Config_Request(name=self.lc_name, image_ref=self.lc_image_ref,
                                flavor_ref=self.lc_flavor_ref,
                                personality=self.lc_personality,
                                metadata=self.lc_metadata,
                                disk_config=self.lc_disk_config,
                                networks=self.lc_networks,
                                load_balancers=self.lc_load_balancers)
        group = Group_Request(name=self.gc_name, cooldown=self.gc_cooldown,
                              min_entities=self.gc_min_entities,
                              max_entities=self.gc_max_entities,
                              metadata=self.gc_metadata)
        config_json = config._obj_to_json()
        group_json = group._obj_to_json()
        body = {'groupConfiguration': json.loads(group_json),
                'launchConfiguration': json.loads(config_json)}
        if self.sp_list:
            body['scalingPolicies'] = self.sp_list
        return json.dumps(body)
