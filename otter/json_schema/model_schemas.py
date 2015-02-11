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


def array_type(schema):
    """
    Return array type of given object schema
    """
    return {
        "type": "array",
        "items": schema,
        "uniqueItems": True,
        "required": True
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

webhook_list = array_type(webhook)

policy = deepcopy(group_schemas.policy)
policy['properties']['id'] = _id
for _policy_type in policy['type']:
    _policy_type['properties']['id'] = {}
    _policy_type['properties']['webhooks'] = webhook_list
    _policy_type['properties']['webhooks']['required'] = False

policy_list = array_type(policy)


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

server = {
    "type": "object",
    "description": "Server information stored in model that maps to actual Nova instance",
    "properties": {
        "id": _id,
        "nova_id": {
            "type": "string",
            "description": "Server ID of corresponding nova instance"
        },
        "status": {
            "type": "string",
            "decription": "Status of server. One of 'pending' or 'active'",
            "pattern": "active|pending"
        },
        "lb_info": {
            "type": "object",
            "description": "Load balancer information. Currently leaving its schema open"
        }
    }
}

servers_list = array_type(server)
