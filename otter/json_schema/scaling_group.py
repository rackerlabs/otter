"""
JSON Schemas for the scaling group - the launch config and the general scaling
group configuration.  There are also example configs and launch configs.
"""

launch_config = {
    "type": "object",
    "description": ("Launch configuration options for the scaling group, "
                    "specifying the custom image, etc."),
    "properties": {
        "imageId": {
            "type": "string",
            "description": "The UUID of the image to use to bootrap a server.",
            "required": True
        },
        # Note: Validation of which IDs are acceptible should not happen here.
        # Acceptable values for IDs can be retrieved from:
        #    https://dfw.servers.api.rackspacecloud.com/v2/$account/flavors
        "flavorId": {
            "type": "integer",
            "description": "The flavor ID of server to start up (size).",
            "required": True
        },
        "networks": {
            "type": "array",
            "description": ("One or more networks (isolated, public, and/or "
                            "private) to which new servers should be "
                            "attached.\n\n"
                            "If you want to attach to the private ServiceNet "
                            "or public Internet networks, you must specify "
                            "them explicitly. The UUID for the private "
                            "ServiceNet is "
                            "11111111-1111-1111-1111-111111111111. The UUID "
                            "for the public Internet is "
                            "00000000-0000-0000-0000-000000000000."),
            "required": True,
            "minItems": 1,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "properties": {
                    "uuid": {
                        "type": "string",
                        "required": True
                    }
                },
                "additionalProperties": False
            }
        },
        "loadBalancers": {
            "type": "array",
            "description": ("One or more load balancers to add new servers "
                            "to.  All servers added to this load balancer "
                            "will be enabled, of primary type, and equally "
                            "weighted."),
            "required": False,    # e.g. for workers that pull off a queue
            "minItems": 0,        # can be an empty list
            "uniqueItems": True,  # do not duplicate load balancers
            "items": {
                "type": "object",
                "description": "One load balancer to add new servers to",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": ("The ID of the load balancer to "
                                        "which new servers will be added."),

                        "required": True
                    },
                    "port": {
                        "type": "integer",
                        "description": ("The port number of the service (on "
                                        "the new servers) to load balance on "
                                        "for this particular load balancer."),
                        "required": True
                    },
                },
                "additionalProperties": False
            }
        },
        "volumes": {
            "type": "array",
            "description": ("One or more Cloud Block Storage volumes to add "
                            "to each new server."),
            "required": False,
            "minItems": 0,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "description": ("One Cloud Block Storage volume to add to "
                                "each new server as a particular device, as "
                                "per http://docs.rackspace.com/servers/api/v2/"
                                "cs-devguide/content/"
                                "Attach_Volume_to_Server.html"),
                "properties": {
                    "volumeId": {
                        "type": "string",
                        "description": ("The ID of the volume to attach to "
                                        "new server instances."),
                        "required": True
                    },
                    "device": {
                        "type": "string",
                        "description": ("The name of the device to attach the "
                                        "volume as."),
                        "required": False
                    }
                },
                "additionalProperties": False
            }
        }
    },
    "additionalProperties": False
}


# Valid launch config examples - used for testing the schema and for
# documentation purposes
launch_config_examples = [
    {
        "imageId": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
        "flavorId": 3,
        "networks": [
            {
                "uuid": "00000000-0000-0000-0000-000000000000"
            },
            {
                "uuid": "11111111-1111-1111-1111-111111111111"
            }
        ],
        "loadBalancers": [
            {
                "id": 144,
                "port": 80
            },
            {
                "id": 2200,
                "port": 8081
            }
        ],
        "volumes": [
            {
                "volumeId": "521752a6-acf6-4b2d-bc7a-119f9148cd8c",
                "device": "/dev/sd3"
            }
        ]
    },
    {
        "imageId": "a09e7493-7429-41e1-8d3f-384d7ece09c0",
        "flavorId": 2,
        "networks": [
            {
                "uuid": "00000000-0000-0000-0000-000000000000"
            }
        ]
    }
]


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
