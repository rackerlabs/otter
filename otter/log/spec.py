"""
Format logs based on specification
"""

from copy import deepcopy

from otter.constants import ServiceType
from otter.log.formatters import ERROR_FIELDS, PRIMITIVE_FIELDS

from twisted.python.failure import Failure


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


# Fields that will occur in error details
error_fields = {
    "system": ServiceType,
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


def error_event(event, failure, why):
    """
    Convert event to error with failure and why
    """
    event["isError"] = True
    event["failure"] = failure
    event["why"] = why
    event["original_message"] = event["message"]
    event["message"] = ()
    return event


def SpecificationObserverWrapper(observer):
    """
    Return observer that validates messages based on specification
    and delegates to given observer
    """
    def validating_observer(event_dict):
        try:
            speced_event = get_validated_event(event_dict)
        except (ValueError, TypeError) as e:
            print e
            speced_event = error_event(
                event_dict, Failure(), "Error validating event")
        observer(speced_event)

    return validating_observer


def try_msg_type(msg_type):
    return msg_type is not None and msg_types.get(msg_type, None)


def get_validated_event(event):
    """
    Validate event's message as per msg_types and error details as
    per error_fields

    :return: Validated event
    :raises: `ValueError` or `TypeError` if `event_dict` is not valid
    """
    # Is this message speced?
    if event.get('isError', False):
        msg = try_msg_type(event.get("why", None))
        if msg is None:
            return event
        validate_error(event_dict)
        event['why'] = msg
    else:
        # message is tuple of strings
        msg = try_msg_type(''.join(event["message"]))
        if msg is None:
            return event
        event["message"] = (msg, )

    # Validate non-primitive fields
    for field in set(event) - (PRIMITIVE_FIELDS | ERROR_FIELDS):
        validate_field(fields, field, event[field])

    event["otter_msg_type"] = msg_type
    return event


def validate_field(fields, field, value):
    """
    Validate field value based on its type in fields
    """
    field_type = fields.get(field)
    if field_type is not None:
        raise ValueError('unknown field ' + field)
    print value, field_type
    if not isinstance(value, field_type):
        raise TypeError('{} of unexpected type {}'.format(value, field))


def validate_error(event):
    """
    Validate failure in the event
    """
    details = getattr(eventDict['failure'].value, 'details', None)
    if details is None:
        return

    for field, value in details.iteritems():
        validate_field(error_fields, field, value)
