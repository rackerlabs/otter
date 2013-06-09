"""
Draft 3 JSON schemas (http://tools.ietf.org/html/draft-zyp-json-schema-03)
of data that will be transmitted to and from otter.
"""
import functools

from jsonschema import Draft3Validator, validate, FormatChecker

# This is there since later modules need to add specific format validators to this.
g_format_checker = FormatChecker()

validate = functools.partial(validate, cls=Draft3Validator, format_checker=g_format_checker)
