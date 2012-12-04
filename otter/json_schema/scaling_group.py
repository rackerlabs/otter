"""
JSON Schemas for the scaling group - the launch config and the general scaling
group configuration.  There are also example configs and launch configs.
"""

config = {
    "type": "object",
    "description": ("Configuration options for the scaling group, "
                    "controlling scaling rate, size, and metadata"),
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the scaling group.",
            "maxLength": 256,
            "required": True
        },
        "cooldown": {
            "type": "integer",
            "description": ("Cooldown period before more entities are added, "
                            "given in seconds.  This number must be an "
                            "integer."),
            "minimum": 0,
            "required": True
        },
        "minEntities": {
            "type": "integer",
            "description": ("Minimum number of entities in the scaling group. "
                            "This number must be an integer."),
            "minimum": 0,
            "required": True,
        },
        "maxEntities": {
            "type": ["integer", "null"],
            "description": ("Maximum number of entities in the scaling group. "
                            "Defaults to null, meaning no maximum.  When "
                            "given, this number must be an integer."),
            "minimum": 0,
            "default": None
        },
        "metadata": {
            "type": "object",
            "description": ("User-provided key-value metadata.  Both keys and "
                            "values should be strings not exceeding 256 "
                            "characters in length."),
            "patternProperties": {
                "^.{0,256}$": {
                    "type": "string",
                    "maxLength": 256
                }
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}

# Valid config examples
config_examples = [
    {
        "name": "webheads",
        "cooldown": 30,
        "minEntities": 1
    },
    {
        "name": "workers",
        "cooldown": 60,
        "minEntities": 5,
        "maxEntities": 100,
        "metadata": {
            "firstkey": "this is a string",
            "secondkey": "1",
        }
    }
]
