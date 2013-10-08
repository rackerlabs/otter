"""
JSON schema to be used to verify the return values from implementations of the
model interface.

This is only going to be used internally to verify the schemas returned by the
interface.  Probably easier to test just by asserting simplified dictionaries
so that all the correct data doesn't have to be mocked.

Please delete from this file.
"""
from copy import deepcopy
from otter.json_schema import group_schemas


# unlike updating or inputing a group config, the returned config must actually
# have all the properties
group_config = deepcopy(group_schemas.config)
for property_name in group_config['properties']:
    group_config['properties'][property_name]['required'] = True


_id = {
    "type": "string",
    "required": True
}


policy = deepcopy(group_schemas.policy)
policy['properties']['id'] = _id
for _policy_type in policy['type']:
    _policy_type['properties']['id'] = {}

policy_list = {
    "type": "array",
    "items": policy,
    "uniqueItems": True,
    "required": True
}


# create group and view manifest returns a dictionary with keys being the ids
manifest = {
    "type": "object",
    "description": "Schema returned by the interface for viewing a manifest",
    "properties": {
        "id": _id,
        "state": {},
        "groupConfiguration": group_schemas.config,
        "launchConfiguration": group_schemas.launch_config,
        "scalingPolicies": policy_list
    },
    "additionalProperties": False
}


webhook = deepcopy(group_schemas.webhook)
webhook['properties']['id'] = _id
webhook['properties']['metadata']['required'] = True
webhook['properties']['capability'] = {
    "type": "object",
    "properties": {
        "hash": {
            "type": "string",
            "description": 'The "unguessable" part of the capability URL',
            "required": True,
        },
        "version": {
            "type": "string",
            "description": ("The version of capability generation used to make "
                            "the capabilityHash"),
            "required": True,
            "pattern": "\S+"
        }
    },
    "additionalProperties": False,
    "required": True
}
webhook['required'] = True

webhook_list = {
    "type": "array",
    "items": webhook,
    "uniqueItems": True,
    "required": True
}
