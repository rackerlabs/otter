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


class LoadBalancer(AutoMarshallingModel):
    """
    Marshalling and unmarshalling for create load balancer request and response
    """

    ROOT_TAG = 'loadBalancer'

    def __init__(self, name=None, nodes=None, protocol=None, virtualIps=None,
                 accessList=None, algorithm=None, connectionLogging=None,
                 connectionThrottle=None, healthMonitor=None, metadata=None,
                 port=None, sessionPersistence=None, id=None, status=None,
                 nodeCount=None, created=None, updated=None,
                 contentCaching=None, halfClosed=None, timeout=None,
                 cluster=None, sourceAddresses=None, sslTermination=None,
                 httpsRedirect=None):
        self.name = name
        self.nodes = nodes
        self.protocol = protocol
        self.virtualIps = virtualIps
        self.accessList = accessList
        self.algorithm = algorithm
        self.connectionLogging = connectionLogging
        self.connectionThrottle = connectionThrottle
        self.healthMonitor = healthMonitor
        self.metadata = metadata
        self.port = port
        self.sessionPersistence = sessionPersistence
        self.id = id
        self.status = status
        self.nodeCount = nodeCount
        self.created = created
        self.updated = updated
        self.contentCaching = contentCaching
        self.halfClosed = halfClosed
        self.timeout = timeout
        self.cluster = cluster
        self.sourceAddresses = sourceAddresses
        self.sslTermination = sslTermination
        self.httpsRedirect = httpsRedirect

    def get_public_ipv4_vip(self):
        """
        gets public ipv4 addresses
        """
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV4' and vip.type == 'PUBLIC':
                return vip

    def get_public_ipv6_vip(self):
        """
        gets public ipv6 addresses
        """
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV6' and vip.type == 'PUBLIC':
                return vip

    def get_servicenet_ipv4_vip(self):
        """
        gets service net ipv4 addresses
        """
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV4' and vip.type == 'SERVICENET':
                return vip

    def _obj_to_json(self):
        """
        Marshalling from object to json
        """
        ret = self._auto_to_dict()
        return json.dumps(ret)

    def _obj_to_dict(self):
        """
        Marshalling from object to dict
        """
        ret = {}
        for attr in vars(self).keys():
            value = vars(self).get(attr)
            if value is not None and attr != '_log':
                ret[attr] = self._auto_value_to_dict(value)

        if hasattr(self, 'ROOT_TAG'):
            return {self.ROOT_TAG: ret}
        else:
            return ret

    def _auto_value_to_dict(self, value):
        """
        converts value to dict
        """
        ret = None
        if isinstance(value, (int, str, unicode, bool)):
            ret = value
        elif isinstance(value, list):
            ret = []
            for item in value:
                ret.append(self._auto_value_to_dict(item))
        elif isinstance(value, dict):
            ret = {}
            for key in value.keys():
                ret[key] = self._auto_value_to_dict(value[key])
        elif isinstance(value, AutoMarshallingModel):
            ret = value._obj_to_dict()
        return ret

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Used to marshal create load balancer request to Load balancer object type
        """
        json_dict = json.loads(serialized_str)
        if cls.ROOT_TAG not in json_dict:
            return None
        ret = cls._dict_to_obj(json_dict.get(cls.ROOT_TAG))
        return ret

    @classmethod
    def _dict_to_obj(cls, dic):
        """
        Used to marshal create load balancer response to Load balancer object type
        """
        if 'nodes' in dic:
            node_list = dic.get('nodes')
            dic[NodeList.ROOT_TAG] = NodeList._dict_to_obj(node_list)
        return LoadBalancer(**dic)
