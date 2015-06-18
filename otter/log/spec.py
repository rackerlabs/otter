"""
Format logs based on specification
"""

from twisted.python.failure import Failure


# mapping from msg type -> message
msg_types = {
    # Keep these in alphabetical order so merges can be deterministic
    "add-server-clb": ("Adding {server_id} with IP address {ip_address} "
                       "to CLB {clb_id}"),
    "converge-all-groups": "Attempting to converge all dirty groups",
    "converge-all-groups-error": "Error while converging all groups",
    "converge-fatal-error": (
        "Fatal error while converging group {scaling_group_id}."),
    "converge-non-fatal-error": (
        "Non-fatal error while converging group {scaling_group_id}"),
    "cf-add-failure": "Failed to add event to cloud feeds",
    "cf-unsuitable-message": (
        "Tried to add unsuitable message in cloud feeds: "
        "{unsuitable_message}"),
    "delete-server": "Deleting {server_id} server",
    "execute-convergence": "Executing convergence",
    "execute-convergence-results": (
        "Got result of {worst_status} after executing convergence"),
    "group-status-active": "Group's status is changed to ACTIVE",
    "group-status-error":
        "Group's status is changed to ERROR. Reasons: {reasons}",
    "launch-servers": "Launching {num_servers} servers",
    "mark-clean-success": "Marked group {scaling_group_id} clean",
    "mark-clean-failure": "Failed to mark group {scaling_group_id} clean",
    "mark-dirty-success": "Marked group {scaling_group_id} dirty",
    "mark-dirty-failure": "Failed to mark group {scaling_group_id} dirty",
    "remove-server-clb": ("Removing server {server_id} with IP address "
                          "{ip_address} from CLB {clb_id}"),
}


def error_event(event, failure, why):
    """
    Convert event to error with failure and why
    """
    return {"isError": True, "failure": failure,
            "why": why, "original_event": event, "message": ()}


class MsgTypeNotFound(Exception):
    """
    Raised when msg_type is not found
    """


def try_msg_types(*tries):
    """
    Try series of msg_types
    """
    for msg_type in tries:
        if msg_type in msg_types:
            return msg_types[msg_type], msg_type
    raise MsgTypeNotFound


def get_validated_event(event):
    """
    Validate event's message as per msg_types and error details as
    per error_fields

    :return: Validated event
    :raises: `ValueError` or `TypeError` if `event_dict` is not valid
    """
    try:
        # message is tuple of strings
        message = ''.join(event.get("message", []))

        # Is this message speced?
        if event.get('isError', False):
            expanded, msg_type = try_msg_types(event.get("why", None), message)
            validate_error(event)
            event['why'] = expanded
            if message:
                event['message'] = (expanded,)
        else:
            expanded, msg_type = try_msg_types(message)
            event["message"] = (expanded, )

        # TODO: Validate non-primitive fields
        event["otter_msg_type"] = msg_type
        return event
    except MsgTypeNotFound:
        return event


def SpecificationObserverWrapper(observer,
                                 get_validated_event=get_validated_event):
    """
    Return observer that validates messages based on specification
    and delegates to given observer.

    Messages are expected to be logged like

    >>> log.msg("launch-servers", num_servers=2)

    where "launch-servers" is message type that will be expanded based on
    entry in msg_types. For errors, the string should be provided in
    "why" field like:

    >>> log.err(f, "execute-convergence-error")
    """
    def validating_observer(event_dict):
        try:
            speced_event = get_validated_event(event_dict)
        except (ValueError, TypeError):
            speced_event = error_event(
                event_dict, Failure(), "Error validating event")
        observer(speced_event)

    return validating_observer


def validate_error(event):
    """
    Validate failure in the event
    """
    # TODO: Left blank to fill implementation using JSON schema
