"""
Marshalling for group state responses
"""
from cafe.engine.models.base import AutoMarshallingModel
from autoscale.models.servers import Metadata, Network, \
    Links, Personality
import re


class Active(AutoMarshallingModel):
    """
    Marshalling for group state's active state
    """

    def __init__(self, **kwargs):
        super(Active, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        ret = []
        for k in serialized_str:
            s = cls._dict_to_obj(k)
            ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, group_dict):
        """
        Helper method to turn dictionary into Group instance
        """
        group = Active(**group_dict)
        if hasattr(group, 'links'):
            group.links = Links._dict_to_obj(group.links)
        for each in group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(group, newkey, group_dict[each])
        return group


class Pending(AutoMarshallingModel):
    """
    Marshalling for group state's pending state
    """

    def __init__(self, **kwargs):
        super(Pending, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        ret = []
        for k in serialized_str:
            s = cls._dict_to_obj(k)
            ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, group_dict):
        """Helper method to turn dictionary into Group instance."""
        group = Pending(**group_dict)
        if hasattr(group, 'links'):
            group.links = Links._dict_to_obj(group.links)
        for each in group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(group, newkey, group_dict[each])
        return group


class Server(AutoMarshallingModel):
    """
    Marshalling for server
    """

    def __init__(self, **kwargs):
        super(Server, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        ret = cls._dict_to_obj(serialized_str)
        return ret

    @classmethod
    def _dict_to_obj(cls, group_dict):
        """
        Helper method to turn dictionary into Group instance
        """
        group = Server(**group_dict)
        attr_list = ['flavorRef', 'name', 'image_ref', 'OS-DCF:diskconfig']
        if hasattr(group, 'metadata'):
            group.metadata = Metadata._dict_to_obj(group.metadata)
        if hasattr(group, 'networks'):
            group.networks = Network._json_to_obj(group.networks)
        if hasattr(group, 'personality'):
            group.personality = Personality._json_to_obj(group.personality)
        for k in attr_list:
            if hasattr(group, k):
                setattr(group, k, getattr(group, k))
        for each in group_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(group, newkey, group_dict[each])
        return group


class Lbaas(AutoMarshallingModel):
    """
    Marshalling for lbaas
    """

    def __init__(self, **kwargs):
        super(Lbaas, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        ret = []
        for k in serialized_str:
            s = cls._dict_to_obj(k)
            ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, lbaas_dict):
        lbaas = Lbaas(**lbaas_dict)
        attr_list = ['loadBalancerId', 'port']
        for k in attr_list:
            if hasattr(lbaas, k):
                setattr(lbaas, k, getattr(lbaas, k))
        return lbaas


class Args(AutoMarshallingModel):
    """
    Marshalling for Args of the scheduler policy
    """

    def __init__(self, **kwargs):
        super(Args, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        return cls._dict_to_obj(serialized_str)

    @classmethod
    def _dict_to_obj(cls, args_dict):
        args = Args(**args_dict)
        for each in args_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(args, newkey, args_dict[each])
        return args
