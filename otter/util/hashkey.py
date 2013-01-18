""" Hash key related library code """
import uuid

""" Cribbed off of the way ELE works """


def generate_key_str(type):
    """
    Generates a random string.

    Generally returns a UUID, but we're accepting a type paramater
    """
    return uuid.uuid5(uuid.NAMESPACE_DNS, "autoscale.api.rackspacecloud.com")
