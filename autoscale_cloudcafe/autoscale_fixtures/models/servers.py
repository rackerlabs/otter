"""
Marshalling for server objects
"""
import json
from cloudcafe.compute.common.equality_tools import EqualityTools
from cafe.engine.models.base import AutoMarshallingModel


class Metadata(AutoMarshallingModel):

    """
    :summary: Metadata Request Object for Server
    """
    def __init__(self, metadata_dict):
        for key, value in metadata_dict.items():
            setattr(self, key, value)

    def _obj_to_json(self):
        ret = self._auto_to_dict()
        return json.dumps(ret)

    @classmethod
    def _dict_to_obj(cls, metadata_dict):
        """
        :summary: Initializes the object from json response
        :param metadata_dict: metadata details
        :type metadata_dict: dictionary
        """
        return Metadata(metadata_dict)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of metadata based on the json
        serialized_str passed in
        """
        json_dict = json.loads(serialized_str)
        if 'metadata' in json_dict.keys():
            metadata_dict = json_dict['metadata']
            return Metadata(metadata_dict)

    @classmethod
    def _obj_to_dict(self, meta_obj):
        meta = {}
        for name in dir(meta_obj):
            value = getattr(meta_obj, name)
            if not name.startswith('_') and not \
                name.startswith('RO') and not name.startswith('deser')\
                    and not name.startswith('sele') and not name.startswith('seria'):
                meta[name] = value
        return meta

    def __eq__(self, other):
        """
        :summary: Overrides the default equals
        :param other: Links object to compare with
        :type other: Links
        :return: True if Links objects are equal, False otherwise
        :rtype: bool
        """
        return EqualityTools.are_objects_equal(self, other)

    def __ne__(self, other):
        """
        :summary: Overrides the default not-equals
        :param other: Links object to compare with
        :type other: Links
        :return: True if Links objects are not equal, False otherwise
        :rtype: bool
        """
        return not self == other


class Links(AutoMarshallingModel):

    """
    :summary: Represents links (url) in the system
    """
    ROOT_TAG = 'links'

    def __init__(self, links_list):
        super(Links, self).__init__()
        self.links = {}
        if links_list is not None:
            for link in links_list:
                self.links[link['rel']] = link['href']
            for key_name in self.links:
                setattr(self, key_name, self.links[key_name])

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """Returns an instance of links based on the json
        serialized_str passed in."""
        json_dict = json.loads(serialized_str)
        if 'links' in json_dict.keys():
            links_list = json_dict['links']
            return Links(links_list)

    @classmethod
    def _dict_to_obj(cls, list_of_links):
        """
        :summary: Initializes the object from json response
        :param list_of_links: links details
        :type list_of_links: list
        """
        return Links(list_of_links)


class Network(AutoMarshallingModel):

    """
    :summary: Represents networks in the system
    """

    def __init__(self, **kwargs):
        super(Network, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """Returns an instance of networks based on the json
        serialized_str passed in."""
        ret = []
        for k in serialized_str:
            s = cls._dict_to_obj(k)
            ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, network_dict):
        network = Network(**network_dict)
        if hasattr(network, 'uuid'):
            setattr(network, 'uuid', getattr(network, 'uuid'))
        return network


class Personality(AutoMarshallingModel):

    """
    :summary: Represents networks in the system
    """

    def __init__(self, **kwargs):
        super(Personality, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of personalitys based on the json
        serialized_str passed in
        """
        ret = []
        for k in serialized_str:
            s = cls._dict_to_obj(k)
            ret.append(s)
        return ret

    @classmethod
    def _dict_to_obj(cls, personality_dict):
        personality = Personality(**personality_dict)
        if hasattr(personality, 'path'):
            setattr(personality, 'path', getattr(personality, 'path'))
        if hasattr(personality, 'content'):
            setattr(personality, 'content', getattr(personality, 'content'))
        return personality
