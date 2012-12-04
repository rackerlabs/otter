"""
Schema validation methods.
"""

import json
import jsonschema
from functools import wraps
from twisted.python.failure import Failure


class InvalidJsonError(Exception):
    """Null"""
    pass


def validate_body(schema):
    """
    Decorator that validates dependent on the schema passed in.
    See http://json-schema.org/ for schema documentation.

    :return: decorator
    """
    def decorator(f):
        @wraps(f)
        def _(request, *args, **kwargs):
            try:
                request.content.seek(0)
                data = json.loads(request.content.read())
                jsonschema.validate(data, schema)
            except ValueError as e:
                return Failure(InvalidJsonError())
            except jsonschema.ValidationError, e:
                return Failure(e)
            kwargs['data'] = data
            return f(request, *args, **kwargs)

        return _
    return decorator
