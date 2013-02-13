"""
Hash key related library code
"""

from hashlib import sha256
import hmac
import uuid


# TODO: do this for real
def _get_hmac_secret(version="1"):
    """
    Given a version number, return cryptographically secure key to be used to
    hash a possibly pseudorandom number as its message

    :return: secret key
    """
    return "sekrit!!!!"


def generate_txnid():
    """
    Generates a transaction ID.

    Generally returns a UUID, but we can always change it later
    """

    return uuid.uuid4()


def generate_key_str(keytype):
    """
    Generates an opaque unique identifier

    Generally returns a UUID, but we're accepting a type paramater
    """
    return uuid.uuid4()


# TODO: versioning
def generate_capability(number=None, version="1"):
    """
    Generates a random number and HMAC it with a secure key to produce
    the an unguessable (due to the super secret key) capability hash.

    :return: a tuple of the the random number, the capability hash (which is
        the number concatenated with the HMAC of the number), and the version
        number of this capability generation scheme.
    :rtype: ``tuple``
    """
    number = number or uuid.uuid4().hex
    version = "1"  # force version to be one
    hashed_number = hmac.new(_get_hmac_secret(version), number, sha256)
    message = "".join((number, hashed_number.hexdigest()))
    return (number, message, version)
