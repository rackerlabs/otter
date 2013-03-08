"""
Hash key related library code
"""

import os
import uuid


def generate_job_id(group_uuid):
    """
    Generates a job ID
    """
    return "{}.{}".format(group_uuid, uuid.uuid4())


def generate_transaction_id():
    """
    Generates a transaction ID.

    Generally returns a UUID, but we can always change it later
    """

    return str(uuid.uuid4())


def generate_key_str(keytype):
    """
    Generates an opaque unique identifier

    Generally returns a UUID, but we're accepting a type paramater
    """
    return str(uuid.uuid4())


# TODO: versioning
def generate_capability():
    """
    Generates a 256-bit random number from /dev/urandom and encodes it as
    64 hex characters.

    :return: a tuple of capability version and the random hex string.
    :rtype: ``tuple``
    """
    return ("1", os.urandom(32).encode('hex'))
