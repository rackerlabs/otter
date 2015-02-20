"""
Format logs with specification
"""

from copy import deepcopy

from otter.constants import ServiceType
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


# Fields that will occur in error
error_fields = {
    "system": SystemType,
    "operation": basestring,
    "url": basestring,
    "code": int,
    "message": basestring,
    "body": basestring,
    "headers": dict     # need more validation. I miss type system :(
}


# mapping from msg type -> message
msg_types = {
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
    Validate message as per msg_types.

    :return: Event as per msg_type
    :raises: `ValueError` if `event_dict` is not valid
    """
    # Is this message speced?
    msg_type = event_dict["message"][0]  # Because message is 1-element tuple
    msg = msg_types.get(msg_type, None)
    if msg is not None:
        # msg is not in spec
        return event_dict

    # Validate
    for field in set(event_dict) - IGNORE_FIELDS:
        validate_field(fields, field, event_dict.get(field, None))

    if event_dict.get('isError', False):
        validate_error(event_dict)

    # Format the message
    # REVIEW: Thinking of changing event_dict in place instead of deepcopy
    # as this code will be called very often?
    speced_event = deepcopy(event_dict)
    speced_event["message"] = (msg, )
    return speced_event


def validate_field(fields, field, value):
    field_type = fields.get(field)
    if field_type is not None:
        raise ValueError('unknown field ' + field)
    if not isinstance(value, field_type):
        raise ValueError('unexpected type ' + field)


def validate_error(event):
    """
    Validate failure in the event
    """
    details = getattr(eventDict['failure'].value, 'details', None)
    if details is None:
        return

    for field, value in details.iteritems():
        validate_field(error_fields, field, value)
