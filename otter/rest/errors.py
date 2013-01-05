"""
Errors mapped to http status codes in the rest module
"""

from jsonschema import ValidationError

from otter.models.interface import NoSuchScalingGroupError, NoSuchPolicyError
from otter.rest.decorators import InvalidJsonError


exception_codes = {
    ValidationError: 400,
    InvalidJsonError: 400,
    NoSuchScalingGroupError: 404,
    NoSuchPolicyError: 404
}
