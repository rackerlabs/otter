"""
Schema to be used to verify the output of the REST endpoints
"""

link = {
    'type': 'array',
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

link_list = {
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'id': {
                'type': ['string', 'integer'],
                'required': True
            },
            'links': link
        },
        'additionalProperties': False
    },
    'uniqueItems': True
}


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
        'active': link_list,
        'pending': link_list
    },
    'additionalProperties': False
}
