"""
JSON schemas for the rest responses from autoscale
"""

from copy import deepcopy

from otter.json_schema.group_schemas import policy, config, launch_config
from otter.json_schema.group_examples import (
    launch_server_config as launch_server_config_examples,
    config as config_examples,
    policy as policy_examples)


#------------- subschemas and other utilities -----------------

links = {
    'type': 'array',
    'description': "Generic schema for a JSON link",
    'required': True,
    'uniqueItems': True,
    'items': {
        'rel': {
            'type': 'string',
            'required': True
        },
        'href': {
            'type': 'string',
            'required': True
        }
    },
    'minLength': 1
}

link_objects = {
    'type': 'object',
    'properties': {
        'id': {
            'type': ['string', 'integer'],
            'required': True
        },
        'links': links
    },
    'additionalProperties': False
}

list_of_links = {
    'type': 'array',
    'items': link_objects,
    'uniqueItems': True,
    'required': True
}


example_url_root = "https://dfw.autoscale.api.rackspacecloud.com"


def make_example_links(group_id):
    """
    Create a dictionary containing links and an ID, for the example responses
    """
    url = "/010101/groups/{0}".format(group_id)
    return {
        "id": group_id,
        "links": [
            {
                "rel": "self",
                "href": "{0}/v1.0/{1}".format(example_url_root, url)
            },
            {
                "rel": "bookmark",
                "href": "{0}/{1}".format(example_url_root, url)
            }
        ]
    }


def _openstackify_schema(key, schema, include_id=False):
    """
    To make responses more open-stack like, wrap everything in a dictionary
    with a particular key corresponding to what the resource is.  Something
    that would validate correctly would look like::

        {
            key: <whatever_would_pass_the_original_schema>
        }

    Also, if the resource needs to include an ID of something, add id and links
    as required properties to this copy of the original schema.
    """
    openstackified = deepcopy(schema)
    openstackified['required'] = True
    if include_id:
        openstackified["properties"].update(link_objects["properties"])

    return {
        "type": "object",
        "properties": {
            key: openstackified
        }
    }

# ----------- endpoint request and response schemas and examples ---------

list_groups_response = {
    "type": "object",
    "properties": {
        "groups": list_of_links,
        "groups_links": links
    },
    "additionalProperties": False
}

group_state = _openstackify_schema("group", {
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
        'active': list_of_links,
        'pending': list_of_links
    },
    'additionalProperties': False
}, True)


view_policy = deepcopy(policy)
view_policy["properties"].update(link_objects["properties"])
for type_blob in view_policy["type"]:
    type_blob["properties"].update(link_objects["properties"])


create_policy_array = {
    "type": "array",
    "items": [policy],
    "uniqueItems": True
}


# ----- schemas for group creation
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

create_group_request_examples = [
    {
        "groupConfiguration": config_examples()[0],
        "launchConfiguration": launch_server_config_examples()[0]
    },
    {
        "groupConfiguration": config_examples()[0],
        "launchConfiguration": launch_server_config_examples()[0],
        "scalingPolicies": [policy_examples()[0]]
    },
    {
        "groupConfiguration": config_examples()[1],
        "launchConfiguration": launch_server_config_examples()[1],
        "scalingPolicies": policy_examples()[1:3]
    }
]

# The response for create group looks almost exactly like the request, except
# that it is wrapped in an extra dictionary with the "group" key and has
create_group_response = _openstackify_schema("group", create_group_request,
                                             True)
create_group_response["description"] = "Schema of the create group response."

create_group_response_examples = [
    {
        "group": {
            "id": "f236a93f-a46d-455c-9403-f26838011522",
            "links": make_example_links("f236a93f-a46d-455c-9403-f26838011522")
        }.update(request)
    }
    for request in create_group_request_examples
]


# ----- schemas for viewing configs
view_config = _openstackify_schema("groupConfiguration", config, False)
view_launch_config = _openstackify_schema("launchConfiguration", launch_config,

                                          False)
# ----- schemas for manifest viewing
view_manifest_response = _openstackify_schema("group", {
    "type": "object",
    "description": ("Schema of the JSON used to display the scaling group's "
                    "manifested view."),
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": {
            "type": "array",
            "items": [view_policy],
            "uniqueItems": True,
            "required": True
        }
    },
    "additionalProperties": False
}, True)
