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
            "default": "",
            "required": True
        },
        "cooldown": {
            "type": "number",
            "description": ("Cooldown period before more entities are added, "
                            "given in seconds."),
            "minimum": 0,
            "required": True
        },
        "minEntities": {
            "type": "integer",
            "description": "Minimum number of entities in the scaling group.",
            "minimum": 0,
            "required": True,
        },
        "maxEntities": {
            "type": ["integer", "null"],
            "description": ("Maximum number of entities in the scaling group. "
                            "Defaults to null, meaning no maximum."),
            "minimum": 0,
            "default": None
        },
        "metadata": {
            "type": "object",
            "description": "User-provided key-value metadata."
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
            "secondkey": [1, 2, 3],
            "thirdkey": {
                "subkey": True
            }
        }
    }
]
