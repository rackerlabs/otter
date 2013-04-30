"""
Errors mapped to http status codes in the rest module
"""

from jsonschema import ValidationError

from otter.controller import CannotExecutePolicyError

from otter.models.interface import (
    GroupNotEmptyError, NoSuchScalingGroupError,
    NoSuchPolicyError, NoSuchWebhookError)

from otter.rest.decorators import InvalidJsonError


exception_codes = {
    ValidationError: 400,
    InvalidJsonError: 400,
    NoSuchScalingGroupError: 404,
    NoSuchPolicyError: 404,
    NoSuchWebhookError: 404,
    GroupNotEmptyError: 409,
    CannotExecutePolicyError: 409,
    NotImplementedError: 501
}
