"""
Marshalling for autoscale reponses
"""
from cafe.engine.models.base import AutoMarshallingModel
import json
import re


class Limits(AutoMarshallingModel):

    """
    works for limits call
    """

    def __init__(self, **kwargs):
        super(Limits, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Limits based on the json
        serialized_str passed in.
        """
        ret = None
        json_dict = json.loads(serialized_str)
        if 'limits' in json_dict.keys():
            ret = cls._dict_to_obj(json_dict['limits'])
        return ret

    @classmethod
    def _dict_to_obj(cls, limits_dict):
        """
        Helper method to turn dictionary into Limit instance
        """
        limits = Limits(** limits_dict)
        if hasattr(limits, 'rate'):
            limits.rate = Rate._json_to_obj(limits.rate)
        if hasattr(limits, 'absolute'):
            limits.absolute = Absolute._json_to_obj(limits.absolute)
        for each in limits_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(limits, newkey, limits_dict[each])
        return limits


class RateLimit(AutoMarshallingModel):

    """
    :summary: Represents networks in the system
    """

    def __init__(self, **kwargs):
        super(RateLimit, self).__init__()
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
    def _dict_to_obj(cls, rate_dict):
        rate = RateLimit(**rate_dict)
        for each in rate_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(rate, newkey, rate_dict[each])
        return rate


class Rate(AutoMarshallingModel):

    """
    :summary: Represents networks in the system
    """

    def __init__(self, **kwargs):
        super(Rate, self).__init__()
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
    def _dict_to_obj(cls, rate_dict):
        rate = Rate(**rate_dict)
        if hasattr(rate, 'regex'):
            setattr(rate, 'regex', getattr(rate, 'regex'))
        if hasattr(rate, 'uri'):
            setattr(rate, 'uri', getattr(rate, 'uri'))
        if hasattr(rate, 'limit'):
            rate.limit = RateLimit._json_to_obj(rate.limit)
        for each in rate_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(rate, newkey, rate_dict[each])
        return rate


class Absolute(AutoMarshallingModel):

    """
    Absolute limit
    """

    def __init__(self, **kwargs):
        super(Absolute, self).__init__()
        for keys, values in kwargs.items():
            setattr(self, keys, values)

    @classmethod
    def _json_to_obj(cls, serialized_str):
        """
        Returns an instance of a Absolute based on the json
        serialized_str passed in.
        """
        return cls._dict_to_obj(serialized_str)

    @classmethod
    def _dict_to_obj(cls, absolute_dict):
        """
        Helper method to turn dictionary into Webhook instance
        """
        absolute = Absolute(**absolute_dict)
        for each in absolute_dict:
            if each.startswith('{'):
                newkey = re.split('}', each)[1]
                setattr(absolute, newkey, absolute_dict[each])
        return absolute
