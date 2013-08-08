"""
Marshalling for server objects
"""
import json
import re
from cafe.engine.models.base import AutoMarshallingModel


class NodeList(AutoMarshallingModel):

    """
    An object that represents the list of Load Balancer Nodes
    """

    def __init__(self, **kwargs):
        super(NodeList, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Lbaas based on the json serialized_str
        passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'nodes' in json_dict.keys():
            ret = []
            for node in json_dict['nodes']:
                s = cls._dict_to_obj(node)
                ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, node_dict):
        """
        Helper method to turn dictionary into Group instance.
        """
        node = NodeList(**node_dict)
        for each in node_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(node, newkey, node_dict[each])
        return node
