"""
JSON schemas for the rest responses from autoscale
"""

from copy import deepcopy
from itertools import cycle

from otter.json_schema.group_schemas import metadata, policy, config, launch_config
from otter.json_schema.group_examples import (
    launch_server_config as launch_server_config_examples,
    config as config_examples,
    policy as policy_examples)


#------------- subschemas and other utilities -----------------

_links = {
    'type': 'array',
    'description': "Generic schema for a JSON link",
    'required': True,
    'uniqueItems': True,
    'items': {
        'type': 'object',
        'properties': {
            'rel': {
                'type': 'string',
                'required': True
            },
            'href': {
                'type': 'string',
                'required': True
            }
        },
        'additionalProperties': False
    }
}

_link_objects = {
    'type': 'object',
    'properties': {
        'id': {
            'type': ['string', 'integer'],
            'required': True
        },
        'links': _links
    },
    'additionalProperties': False
}

_list_of_links = {
    'type': 'array',
    'items': _link_objects,
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


def _openstackify_schema(key, schema, include_id=False, paginated=False):
    """
    To make responses more open-stack like, wrap everything in a dictionary
    with a particular key corresponding to what the resource is.  Something
    that would validate correctly would look like::

        {
            key: <whatever_would_pass_the_original_schema>
        }

    Also, if the resource needs to include an ID of something, add id and links
    as required properties to this copy of the original schema.

    :param key: The openstack key to use
    :type key: ``str``

    :param schema: The actual schema that defines the data
    :type schema: ``dict``

    :param include_id: to embed an id and links key into the schema - is it
        an instance of something
    :type include_id: ``bool``

    :param paginated: Whether to include a list of paginated of links under
        the key "<key>_links"
    :type paginated: ``bool``
    """
    openstackified = deepcopy(schema)
    openstackified['required'] = True
    if include_id:
        openstackified["properties"].update(_link_objects["properties"])
        if isinstance(openstackified["type"], list):
            # include _link_object's properties as properties in the type, so
            # it'd look like:
            # {
            #   <original property>...
            #   'id': {},
            #   ...
            # }
            updated = zip(_link_objects["properties"].keys(),
                          cycle([{}]))

            for schema_type in openstackified['type']:
                if "properties" in schema_type:
                    schema_type["properties"].update(updated)

    properties = {key: openstackified}

    if paginated:
        properties["{0}_links".format(key)] = _links

    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False
    }

# ----------- endpoint request and response schemas and examples ---------

list_groups_response = _openstackify_schema("groups", _list_of_links,
                                            paginated=True)

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
        'active': _list_of_links,
        'pending': _list_of_links
    },
    'additionalProperties': False
}, include_id=True)


# ----- schemas for viewing policies
view_policy = deepcopy(policy)
view_policy["properties"].update(_link_objects["properties"])
for type_blob in view_policy["type"]:
    type_blob["properties"].update(_link_objects["properties"])


_view_policies_list = {
    "type": "array",
    "items": [view_policy],
    "uniqueItems": True,
    "required": True
}


list_policies_response = _openstackify_schema("policies", _view_policies_list,
                                              paginated=True)

create_policies_request = {
    "type": "array",
    "items": [policy],
    "uniqueItems": True
}

create_policies_response = _openstackify_schema("policies", _view_policies_list)


get_policy_response = _openstackify_schema("policy", policy, include_id=True)


# ----- schemas for group creation
create_group_request = {
    "type": "object",
    "description": "Schema of the JSON used to create a scaling group.",
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": create_policies_request
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
                                             include_id=True)
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
view_config = _openstackify_schema("groupConfiguration", config)
view_launch_config = _openstackify_schema("launchConfiguration", launch_config)


# ----- schemas for manifest viewing
view_manifest_response = _openstackify_schema("group", {
    "type": "object",
    "description": ("Schema of the JSON used to display the scaling group's "
                    "manifested view."),
    "properties": {
        "groupConfiguration": config,
        "launchConfiguration": launch_config,
        "scalingPolicies": _view_policies_list
    },
    "additionalProperties": False
}, include_id=True)


# ----- schemas for viewing webhooks
view_webhook_response = {
    "type": "object",
    "description": "Schema of the JSON used to display a webhook.",
    "properties": {"metadata": metadata},
    "additionalProperties": False
}
view_webhook_response["properties"].update(_link_objects["properties"])


list_webhooks_response = _openstackify_schema("webhooks", {
    "type": "array",
    "items": [view_webhook_response],
    "uniqueItems": True
}, paginated=True)
