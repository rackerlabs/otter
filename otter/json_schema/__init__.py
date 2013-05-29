"""
Draft 3 JSON schemas (http://tools.ietf.org/html/draft-zyp-json-schema-03)
of data that will be transmitted to and from otter.
"""
import functools

from jsonschema import Draft3Validator, validate

validate = functools.partial(validate, cls=Draft3Validator)
