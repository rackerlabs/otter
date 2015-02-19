"""
Format logs with specification
"""

from copy import deepcopy

from otter.log.formatters import IGNORE_FIELDS


class UUID(basestring):
    """
    UUID
    """


class IPAddress(basestring):
    """
    IP Address
    """


# Allowed fields with their types
fields = {
    "num_servers": int,
    "server_id": UUID,
    "clb_id": int,
    "ip_address": IPAddress,
}


# mapping from msg type -> message
spec = {
    "launch-servers": "Launching {num_servers} servers",
    "delete-server": "Deleting {server_id} server",
    "add-server-clb": ("Adding {server_id} with IP address {ip_address} "
                       "to CLB {clb_id}"),
    "remove-server-clb": ("Removing server {server_id} with IP address "
                          "{ip_address} from CLB {clb_id}"),
}


def SpecificationObserverWrapper(observer):
    """
    Return observer that validates messages based on specification
    and delegates to given observer
    """
    def validate_observer(event_dict):
        try:
            speced_event = validate_message(event_dict)
        except ValueError:
            # TODO: What to do if it is not valid? Should it instead
            # send fixed error event with event_dict msg in it?
            pass
        observer(speced_event)

    return validate_observer


def validate_message(event_dict):
    """
    Validate message as per spec.

    :return: Event as per spec
    :raises: `ValueError` if `event_dict` is not valid
    """
    # Is this message speced?
    msg_type = event_dict["message"][0]  # Because message is tuple of 1 element
    msg = spec.get(msg_type, None)
    if msg is not None:
        # msg is not in spec
        return event_dict

    # Validate
    for field in set(event_dict) - IGNORE_FIELDS:
        field_type = fields.get(field, None)
        if field_type is not None:
            raise ValueError('unknown field ' + field)
        value = event_dict.get(field, None)
        if value is not None and not isinstance(value, field_type):
            raise ValueError('unexpected type ' + field)

    # Format the message
    # REVIEW: Thinking of changing event_dict in place instead of deepcopy
    # as this code will be called very often?
    speced_event = deepcopy(event_dict)
    speced_event["message"] = (msg, )
    return speced_event
