"""
JSON Schemas that define the scaling group - the launch config, the general
scaling group configuration, and policies.
"""

from copy import deepcopy

# This is built using union types which may not be available in Draft 4
# see: http://stackoverflow.com/questions/9029524/json-schema-specify-field-is-
# required-based-on-value-of-another-field
# and https://groups.google.com/forum/?fromgroups=#!msg/json-
# schema/uvUFu6KE_xQ/O5aTuw5pRYEJ

# It is possible to create an invalid launch config (one that fails to create
# a server) - (1) we don't validate against nova yet, (2) even if it validates
# against nova at creation time, they may delete an image or network, and (3)
# it is possible for the user to create a server that is not connected to
# either the public net or the ServiceNet.

# TODO: we need some strategy for perhaps warning the user that their launch
# config has problems.  Perhaps a no-op validation endpoint that lists all the
# problems with their launch configuration, or perhaps accept the launch
# configuration and return a warning list of all possible problems.

#
# Launch Schemas
#

MAX_ENTITIES = 25

metadata = {
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

launch_server = {
    "type": "object",
    "description": ("'Launch Server' launch configuration options.  This type "
                    "of launch configuration will spin up a next-gen server "
                    "directly with the provided arguments, and add the server "
                    "to one or more load balancers (if load balancer "
                    "arguments are specified."),
    "properties": {
        "type": {
            "enum": ["launch_server"],
        },
        "args": {
            "properties": {
                "server": {
                    "type": "object",
                    # The schema for the create server attributes should come
                    # from Nova, or Nova should provide some no-op method to
                    # validate creating a server.  Autoscale should not
                    # attempt to re-create Nova's validation.
                    "description": (
                        "Attributes to provide to nova create server: "
                        "http://docs.rackspace.com/servers/api/v2/"
                        "cs-devguide/content/CreateServers.html."
                        "Whatever attributes are passed here will apply to "
                        "all new servers (including the name attribute)."),
                    "required": True
                },
                "loadBalancers": {
                    "type": "array",
                    "description": (
                        "One or more load balancers to add new servers to. "
                        "All servers will be added to these load balancers "
                        "with their ServiceNet addresses, and will be "
                        "enabled, of primary type, and equally weighted. If "
                        "new servers are not connected to the ServiceNet, "
                        "they will not be added to any load balancers."),
                    # The network is ServiceNet because CLB doesn't work with
                    # isolated networks, and using public networks will just
                    # get the customer charged for the bandwidth anyway, so it
                    # doesn't seem like a good idea.
                    "required": False,
                    "minItems": 0,
                    "uniqueItems": True,
                    "items": {
                        "type": "object",
                        "description": (
                            "One load balancer all new servers should be "
                            "added to."),
                        "properties": {
                            # load balancer id's are NOT uuid's.  just an int.
                            "loadBalancerId": {
                                "type": "integer",
                                "description": (
                                    "The ID of the load balancer to which new "
                                    "servers will be added."),
                                "required": True
                            },
                            "port": {
                                "type": "integer",
                                "description": (
                                    "The port number of the service (on the "
                                    "new servers) to load balance on for this "
                                    "particular load balancer."),
                                "required": True
                            }
                        },
                        "additionalProperties": False
                    }
                },

            },
            "additionalProperties": False
        }
    }
}

# base launch config
launch_config = {
    "type": [launch_server],
    "properties": {
        "type": {
            "type": "string",
            "description": "The type of launch config this is.",
            "required": True
        },
        "args": {
            "type": "object",
            "required": True
        }
    },
    "additionalProperties": False,
    "required": True
}


config = {
    "type": "object",
    "description": ("Configuration options for the scaling group, "
                    "controlling scaling rate, size, and metadata"),
    "properties": {
        "name": {
            "type": "string",
            "description": ("Name of the scaling group (this name does not "
                            "have to be unique)."),
            "maxLength": 256,
            "required": True,
            "pattern": "\S+"  # must contain non-whitespace
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
            "maximum": MAX_ENTITIES,
            "required": True,
        },
        "maxEntities": {
            "type": ["integer", "null"],
            "description": ("Maximum number of entities in the scaling group. "
                            "Defaults to null, meaning no maximum.  When "
                            "given, this number must be an integer."),
            "minimum": 0,
            "maximum": MAX_ENTITIES,
            "default": None
        },
        "metadata": metadata
    },
    "additionalProperties": False,
    "required": True
}

# Copy and require maxEntities for updates.
update_config = deepcopy(config)
update_config['properties']['maxEntities']['required'] = True

zero = {
    "minimum": 0,
    "maximum": 0
}

policy = {
    "type": [
        {
            "type": "object",
            "properties": {
                "name": {},
                "cooldown": {},
                "type": {},
                "changePercent": {"required": True}
            },
            "additionalProperties": False
        },
        {
            "type": "object",
            "properties": {
                "name": {},
                "cooldown": {},
                "type": {},
                "change": {"required": True}
            },
            "additionalProperties": False
        },
        {
            "type": "object",
            "properties": {
                "name": {},
                "cooldown": {},
                "type": {},
                "desiredCapacity": {"required": True}
            },
            "additionalProperties": False
        }
    ],
    "description": (
        "A Scaling Policy defines how the current number of servers in the "
        "scaling group should change, and how often this exact change can "
        "happen (cooldown)."),
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "A name for this scaling policy. This name does have to be "
                "unique for all scaling policies."),
            "required": True,
            "maxLength": 256,
            "pattern": "\S+"  # must contain non-whitespace
        },
        "change": {
            "type": "integer",
            "description": (
                "A non-zero integer change to make in the number of servers "
                "in the scaling group.  If positive, the number of servers "
                "will increase.  If negative, the number of servers will "
                "decrease."),
            "disallow": [zero]
        },
        "changePercent": {
            "type": "number",
            "description": (
                "A non-zero percent change to make in the number of servers "
                "in the scaling group.  If positive, the number of servers "
                "will increase by the given percentage.  If negative, the "
                "number of servers will decrease by the given percentage. The "
                "absolute change in the number of servers will be rounded "
                "to the nearest integer away than zero. This means that "
                "if -X% of the current number of servers turns out to be "
                "-0.5 or -0.25 or -0.75 servers, the actual number of servers "
                "that will be shut down is 1. And if X% of current number of "
                "servers turn out to be 1.2 or 1.5 or 1.7 servers, the actual "
                "number of servers that will be launched is 2"),
            "disallow": [zero]
        },
        "desiredCapacity": {
            "type": "integer",
            "description": (
                "The desired capacity of the group - i.e. how many servers there "
                "should be (an absolute number, rather than a delta from the "
                "current number of servers). For example, if this is 10 and then "
                "executing policy with this will bring the number of servers to 10."),
            "minimum": 0
        },
        "cooldown": {
            "type": "number",
            "description": (
                "Cooldown period (given in seconds) before this particular "
                "scaling policy can be executed again.  This cooldown period "
                "does not affect the global scaling group cooldown."),
            "minimum": 0,
            "required": True
        },
        "type": {
            "enum": ["webhook"],
            "required": True
        }
    }
}


webhook = {
    "type": "object",
    "description": "A webhook to execute a scaling policy",
    "properties": {
        "name": {
            "type": "string",
            "description": "A name for this webhook for logging purposes",
            "required": True,
            "maxLength": 256,
            "pattern": "\S+"  # must contain non-whitespace
        },
        "metadata": metadata
    },
    "additionalProperties": False
}
