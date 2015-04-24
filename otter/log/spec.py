"""
Format logs based on specification
"""

from twisted.python.failure import Failure


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
        except (ValueError, TypeError):
            speced_event = error_event(
                event_dict, Failure(), "Error validating event")
        observer(speced_event)

    return validating_observer


def try_msg_type(msg_type):
    """
    Try message type and return None if not found
    """
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
        msg_type = event.get("why", None)
        msg = try_msg_type(msg_type)
        if msg is None:
            return event
        validate_error(event)
        event['why'] = msg
    else:
        # message is tuple of strings
        msg_type = ''.join(event["message"])
        msg = try_msg_type(msg_type)
        if msg is None:
            return event
        event["message"] = (msg, )

    # TODO: Validate non-primitive fields

    event["otter_msg_type"] = msg_type
    return event


def validate_error(event):
    """
    Validate failure in the event
    """
    # TODO: Left blank to fill implementation using JSON schema
