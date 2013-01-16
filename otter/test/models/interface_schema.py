"""
JSON schema to be used to verify the return values from implementations of the
model interface.
"""
from copy import deepcopy

from otter.json_schema.group_schemas import config as input_config
from otter.test.rest.response_schema import group_state as rest_group_state

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


# the active/pending format is what differs between the model interface output
# and the rest response ouptut
group_state = deepcopy(rest_group_state)
for key in ('active', 'pending'):
    group_state['properties'][key] = entity_schema


# unlike updating or inputing a group config, the returned config must actually
# have all the properties
group_config = deepcopy(input_config)
for property_name in group_config['properties']:
    group_config['properties'][property_name]['required'] = True
