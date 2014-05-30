"""
Errors mapped to http status codes in the rest module
"""

from jsonschema import ValidationError

from otter.controller import CannotExecutePolicyError
from otter.supervisor import ServerNotFoundError, ServersBelowMinError

from otter.models.interface import (
    GroupNotEmptyError, NoSuchScalingGroupError,
    NoSuchPolicyError, NoSuchWebhookError, ScalingGroupOverLimitError,
    WebhooksOverLimitError, PoliciesOverLimitError)

from otter.worker.validate_config import InvalidLaunchConfiguration

from otter.rest.decorators import InvalidJsonError, InvalidQueryArgument


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
    ServersBelowMinError: 403,
    CannotExecutePolicyError: 403,
    InvalidQueryArgument: 400,
    NotImplementedError: 501,
    ScalingGroupOverLimitError: 422,
    WebhooksOverLimitError: 422,
    PoliciesOverLimitError: 422
}
