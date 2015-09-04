"""
Errors mapped to http status codes in the rest module
"""

from jsonschema import ValidationError

from otter.controller import CannotExecutePolicyError, GroupPausedError
from otter.models.interface import (
    GroupNotEmptyError, NoSuchPolicyError, NoSuchScalingGroupError,
    NoSuchWebhookError, PoliciesOverLimitError,
    ScalingGroupOverLimitError, WebhooksOverLimitError)
from otter.rest.decorators import InvalidJsonError, InvalidQueryArgument
from otter.supervisor import (
    CannotDeleteServerBelowMinError, ServerNotFoundError)
from otter.worker.validate_config import InvalidLaunchConfiguration


class InvalidMinEntities(Exception):
    """
    Something is wrong with the minEntities values.
    """

exception_codes = {
    InvalidMinEntities: 400,
    ValidationError: 400,
    InvalidLaunchConfiguration: 400,
    InvalidJsonError: 400,
    NoSuchScalingGroupError: 404,
    NoSuchPolicyError: 404,
    NoSuchWebhookError: 404,
    ServerNotFoundError: 404,
    GroupNotEmptyError: 403,
    GroupPausedError: 403,
    CannotDeleteServerBelowMinError: 403,
    CannotExecutePolicyError: 403,
    InvalidQueryArgument: 400,
    NotImplementedError: 501,
    ScalingGroupOverLimitError: 422,
    WebhooksOverLimitError: 422,
    PoliciesOverLimitError: 422
}
