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

    ROOT_TAG = 'loadBalancer'

    def __init__(self, name=None, nodes=None, protocol=None, virtualIps=None,
                 accessList=None, algorithm=None, connectionLogging=None,
                 connectionThrottle=None, healthMonitor=None, metadata=None,
                 port=None, sessionPersistence=None, id=None, status=None,
                 nodeCount=None, created=None, updated=None,
                 contentCaching=None, halfClosed=None, timeout=None,
                 cluster=None, sourceAddresses=None, sslTermination=None,
                 httpsRedirect=None):
        '''An object that represents the data of a Load Balancer.'''
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
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV4' and vip.type == 'PUBLIC':
                return vip

    def get_public_ipv6_vip(self):
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV6' and vip.type == 'PUBLIC':
                return vip

    def get_servicenet_ipv4_vip(self):
        for vip in self.virtualIps:
            if vip.ipVersion == 'IPV4' and vip.type == 'SERVICENET':
                return vip

    def _obj_to_json(self):
        ret = self._auto_to_dict()
        return json.dumps(ret)

    def _obj_to_dict(self):
        ret = {}
        for attr in vars(self).keys():
            value = vars(self).get(attr)
            #quick and dirty fix for _log getting added in
            #ideally _log should be __log, talk to Jose about this.
            if value is not None and attr != '_log':
                ret[attr] = self._auto_value_to_dict(value)

        if hasattr(self, 'ROOT_TAG'):
            return {self.ROOT_TAG: ret}
        else:
            return ret

    def _auto_value_to_dict(self, value):
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
        json_dict = json.loads(serialized_str)
        if cls.ROOT_TAG not in json_dict:
            return None
        ret = cls._dict_to_obj(json_dict.get(cls.ROOT_TAG))
        return ret

    @classmethod
    def _dict_to_obj(cls, dic):
        if 'nodes' in dic:
            node_list = dic.get('nodes')
            dic[NodeList.ROOT_TAG] = NodeList._dict_to_obj(node_list)
        # if VirtualIpList.ROOT_TAG in dic:
        #     vip_list = dic.get(VirtualIpList.ROOT_TAG)
        #     dic[VirtualIpList.ROOT_TAG] = \
        #         VirtualIpList._dict_to_obj(vip_list)
        # if Created.ROOT_TAG in dic:
        #     created = dic.get(Created.ROOT_TAG)
        #     dic[Created.ROOT_TAG] = Created._dict_to_obj(created)
        # if Updated.ROOT_TAG in dic:
        #     updated = dic.get(Updated.ROOT_TAG)
        #     dic[Updated.ROOT_TAG] = Updated._dict_to_obj(updated)
        # if SourceAddresses.ROOT_TAG in dic:
        #     s_addrs = dic.get(SourceAddresses.ROOT_TAG)
        #     dic[SourceAddresses.ROOT_TAG] = \
        #         SourceAddresses._dict_to_obj(s_addrs)
        # if Cluster.ROOT_TAG in dic:
        #     cluster = dic.get(Cluster.ROOT_TAG)
        #     dic[Cluster.ROOT_TAG] = Cluster._dict_to_obj(cluster)
        # if ContentCaching.ROOT_TAG in dic:
        #     cc = dic.get(ContentCaching.ROOT_TAG)
        #     dic[ContentCaching.ROOT_TAG] = ContentCaching._dict_to_obj(cc)
        # if ConnectionLogging.ROOT_TAG in dic:
        #     cl = dic.get(ConnectionLogging.ROOT_TAG)
        #     dic[ConnectionLogging.ROOT_TAG] = \
        #         ConnectionLogging._dict_to_obj(cl)
        # if SessionPersistence.ROOT_TAG in dic:
        #     sp = dic.get(SessionPersistence.ROOT_TAG)
        #     dic[SessionPersistence.ROOT_TAG] = \
        #         SessionPersistence._dict_to_obj(sp)
        # if AccessList.ROOT_TAG in dic:
        #     al = dic.get(AccessList.ROOT_TAG)
        #     dic[AccessList.ROOT_TAG] = AccessList._dict_to_obj(al)
        # if ConnectionThrottle.ROOT_TAG in dic:
        #     ct = dic.get(ConnectionThrottle.ROOT_TAG)
        #     dic[ConnectionThrottle.ROOT_TAG] = \
        #         ConnectionThrottle._dict_to_obj(ct)
        # if HealthMonitor.ROOT_TAG in dic:
        #     hm = dic.get(HealthMonitor.ROOT_TAG)
        #     dic[HealthMonitor.ROOT_TAG] = HealthMonitor._dict_to_obj(hm)
        # if Metadata.ROOT_TAG in dic:
        #     md = dic.get(Metadata.ROOT_TAG)
        #     dic[Metadata.ROOT_TAG] = Metadata._dict_to_obj(md)
        # if SSLTermination.ROOT_TAG in dic:
        #     ssl = dic.get(SSLTermination.ROOT_TAG)
        #     dic[SSLTermination.ROOT_TAG] = SSLTermination._dict_to_obj(ssl)
        return LoadBalancer(**dic)
