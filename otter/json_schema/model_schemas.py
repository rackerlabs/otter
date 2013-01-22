"""
JSON schema to be used to verify the return values from implementations of the
model interface.
"""
from copy import deepcopy
from otter.json_schema.group_schemas import config, launch_config, policy

entity_schema = {
    'type': 'object',
    'patternProperties': {
        "^\S+$": {
            'type': 'array',
            'required': True,
            'uniqueItems': True,
            'minItems': 1,
            'items': {
                "type": "object",
                "properties": {
                    'rel': {
                        'type': 'string',
                        'required': True
                    },
                    'href': {
                        'type': 'string',
                        'required': True
                    }
                },
                "additionalProperties": False
            }
        }
    },
    'additionalProperties': False
}

# example:
# {
#   "active": {
#     "{instanceId1}": [
#       {
#         "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId1}",
#         "rel": "self"
#       },
#       {
#         "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId1}",
#         "rel": "bookmark"
#       }
#     ]
#   },
#   "pending": {
#     "{instanceId2}": [
#       {
#         "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId2},
#         "rel": "self"
#       },
#       {
#         "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/{instanceId2}"
#         "rel": "bookmark"
#       }
#     ]
#   },
#   "steadyState": 2,
#   "paused": false
# }
group_state = {
    'type': 'object',
    'properties': {
        'steadyState': {
            'type': 'integer',
            'minimum': 0,
            'required': True
        },
        'paused': {
            'type': 'boolean',
            'required': True
        },
        'active': entity_schema,
        'pending': entity_schema
    },
    'additionalProperties': False
}

# unlike updating or inputing a group config, the returned config must actually
# have all the properties
group_config = deepcopy(config)
for property_name in group_config['properties']:
    group_config['properties'][property_name]['required'] = True


# view manifest returns a dictionary with keys being the ids
view_manifest = {
    "type": "object",
    "description": "Schema returned by the interface for viewing a manifest",
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": {
            "type": "object",
            "patternProperties": {
                "^\S+$": {
                    "type": "object",
                    "required": True,
                    "items": [policy]
                }
            },
            "required": True,
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}
