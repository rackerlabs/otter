"""
JSON schemas for the rest responses from autoscale
"""

from otter.json_schema.group_schemas import policy, config, launch_config
from otter.json_schema.group_examples import (
    launch_server_config as launch_server_config_examples,
    config as config_examples,
    policy as policy_examples)


create_policy_array = {
    "type": "array",
    "items": [policy],
    "uniqueItems": True
}


policy_list = {
    "type": "object",
    "patternProperties": {
        "^\S+$": {
            "type": "object",
            "required": True,
            "items": [policy]
        }
    },
    "required": False,
    "additionalProperties": False
}


policy_list_examples = {
    "f236a93f-a46d-455c-9403-f26838011522": {
        "name": "scale up by 10",
        "change": 10,
        "cooldown": 5
    },
    "e27040e5-527e-4710-b8a9-98e5e9aff2f0": {
        "name": "scale down a 5.5 percent because of a tweet",
        "changePercent": -5.5,
        "cooldown": 6
    },
    "228dbf91-7b15-4d21-8de2-fa584f01a440": {
        "name": "set number of servers to 10",
        "steadyState": 10,
        "cooldown": 3
    }
}


# Schemas for group creation
create_group_request = {
    "type": "object",
    "description": "Schema of the JSON used to create a scaling group.",
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": {
            "type": "array",
            "items": [policy],
            "uniqueItems": True
        }
    },
    "additionalProperties": False
}


create_group_response = {
    "type": "object",
    "description": "Schema of the JSON returned from creating a scaling group.",
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": policy_list
    },
    "additionalProperties": False
}

create_group_request_examples = [
    {
        "groupConfiguration": config_examples[0],
        "launchConfiguration": launch_server_config_examples[0]
    },
    {
        "groupConfiguration": config_examples[0],
        "launchConfiguration": launch_server_config_examples[0],
        "scalingPolicies": [policy_examples[0]]
    },
    {
        "groupConfiguration": config_examples[1],
        "launchConfiguration": launch_server_config_examples[1],
        "scalingPolicies": [policy_examples[1], policy_examples[2]]
    }
]
