""" Hash key related library code """
import uuid


def generate_key_str(keytype):
    """
    Generates an opaque unique identifier

    Generally returns a UUID, but we're accepting a type paramater
    """
    return uuid.uuid4()
