"""
Functions for resolving authentication information.
"""


def authenticate_tenant(tenant_id):
    """
    Authenticate as the desired tenant.

    :params tenant_id: id of the tenant to authenticate as
    :returns: Deferred that fires with a 2-tuple of auth token and service catalog.
    """

    raise NotImplementedError()
