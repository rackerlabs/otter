"""
JSON Schemas that define the scaling group - the launch config, the general
scaling group configuration, and policies.
"""

from copy import deepcopy
from datetime import datetime

from croniter import croniter

from iso8601 import ParseError

from jsonschema import ValidationError

from toolz import get_in

from otter.json_schema import format_checker
from otter.util.timestamp import timestamp_to_epoch

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

MAX_ENTITIES = 1000
MAX_COOLDOWN = 86400   # 24 * 60 * 60

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

server_metadata = {
    # TODO: Taken from Nova's validation code at
    # https://github.com/openstack/nova/blob/master/nova/api/validation/parameter_types.py#L83.
    # It will be ideal to import nova package and use their schema but their
    # schema is not fully complete and there are lots of dependencies when trying to
    # install nova package
    "type": "object",
    "patternProperties": {
        "^[a-zA-Z0-9-_:. ]{1,255}$": {
            "type": "string", "maxLength": 255
        }
    },
    "additionalProperties": False,
}

# nova server payload

_bfv_server = {
    "type": "object",
    "properties": {
        "imageRef": {
            "type": ["string", "null"],
            "maxLength": 0
        },
        "block_device_mapping": {
            "type": "array",
            "items": {"type": "object"},
            "required": True
        }
    }
}

_bfv2_server = deepcopy(_bfv_server)
_bdm = _bfv2_server["properties"].pop("block_device_mapping")
_bfv2_server["properties"]["block_device_mapping_v2"] = _bdm

_non_bfv_server = {
    "type": "object",
    "properties": {
        "imageRef": {
            "type": "string",
            "pattern": "^\S+$",  # must contain non-whitespace
            "required": True
        }
    }
}

_rcv3_lb = {
    "type": "object",
    "description": (
        "One load balancer all new servers should be "
        "added to."),
    "properties": {
        "loadBalancerId": {
            "type": "string",
            "pattern": "^\S+$",  # must contain non-whitespace
            "required": True,
            "description": (
                "The ID of the load balancer to which new "
                "servers will be added."),
        },
        "type": {
            "type": "string",
            "description": (
                "What type of a load balancer is in use"),
            "required": True,
            "pattern": "^RackConnectV3$"
        }
    },
    "additionalProperties": False
}

_clb_lb = {
    "type": "object",
    "description": (
        "One load balancer all new servers should be "
        "added to."),
    "properties": {
        # Cloud load balancer id's are NOT uuid's, just ints.  But accept
        # strings also for backwards compatibility reasons.
        "loadBalancerId": {
            "type": ["integer", {"type": "string", "pattern": "^\S+$"}],
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
                "particular Cloud Load Balancer."),
            "required": True
        },
        "type": {
            "type": "string",
            "description": (
                "What type of a load balancer is in use"),
            "required": False,
            "pattern": "^CloudLoadBalancer$"
        }
    },
    "additionalProperties": False
}


server = {
    "type": [_bfv_server, _bfv2_server, _non_bfv_server],
    # The schema for the create server attributes should come
    # from Nova, or Nova should provide some no-op method to
    # validate creating a server. Autoscale should not
    # attempt to re-create Nova's validation. But since otter has decided
    # to do some level of sanity checking, this schema validates subset of instance that
    # is getting validated in code
    "description": ("Attributes to provide to nova create server: "
                    "https://docs.rackspace.com/servers/api/v2/"
                    "cs-devguide/content/CreateServers.html."
                    "Whatever attributes are passed here will apply to "
                    "all new servers (including the name attribute)."),
    "properties": {
        "imageRef": {
        },
        "flavorRef": {
            "type": "string",
            "required": True,
            "minLength": 1,
            "pattern": "^\S+$"  # must contain non-whitespace
        },
        "block_device_mapping": {
            "type": "array",
            "items": {"type": "object"}
        },
        "personality": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "maxLength": 255,
                        "minLength": 1,
                        "required": True
                    },
                    "contents": {"type": "string", "required": True}
                }
            },
            "required": False
        },
        "metadata": {
            "type": [server_metadata, "null"],
            "required": False
        }
    },
    "required": True
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
                "server": server,
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
                    "maxItems": 5,
                    "uniqueItems": True,
                    "items": {
                        "type": [_clb_lb, _rcv3_lb]
                    }
                },
                "draining_timeout": {
                    "type": "number",
                    "description": (
                        "Number of seconds the server will be put in draining "
                        "before removing it from load balancer. The load "
                        "balancer can be CLB or RCv3"),
                    "required": False,
                    "minimum": 30,
                    "maximum": 3600  # 1 hour
                }
            },
            "additionalProperties": False
        }
    }
}

_stack_template_url = {
    "type": "object",
    "properties": {
        "template": {
            "disallow": "any"
        },
        "template_url": {
            "required": True
        },
    }
}

_stack_template_inline = {
    "type": "object",
    "properties": {
        "template": {
            "required": True
        },
        "template_url": {
            "disallow": "any"
        }
    }
}

stack = {
    "type": [_stack_template_url, _stack_template_inline],
    "properties": {
        "disable_rollback": {
            "type": "boolean",
            "required": False
        },
        "environment": {
            "type": ["string", "object"],
            "required": False
        },
        "files": {
            "type": "object",
            "required": False
        },
        "parameters": {
            "type": "object",
            "required": False
        },
        "template": {
            "type": ["string", "object"],
            "required": False
        },
        "template_url": {
            "type": "string",
            "required": False
        },
        "timeout_mins": {
            "type": "number",
            "required": False
        },
    },
    "additionalProperties": False
}

launch_stack = {
    "type": "object",
    "description": ("'Launch Stack' launch configuration options.  This type "
                    "of launch configuration will spin up a Heat stack "
                    "directly with the provided arguments, and add the IP the "
                    "stack outputs to one or more load balancers (if load "
                    "balancer arguments are specified."),
    "properties": {
        "type": {
            "enum": ["launch_stack"],
        },
        "args": {
            "type": "object",
            "properties": {
                "stack": stack
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}

# base launch config
launch_config = {
    "type": [launch_server, launch_stack],
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
                            "integer. Min is 0 seconds, max is 86400 seconds "
                            "(24 hrs * 60 min * 60 sec)."),
            "minimum": 0,
            "maximum": MAX_COOLDOWN,
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
update_config['properties']['metadata']['required'] = True

zero = {
    "minimum": 0,
    "maximum": 0
}


def validate_launch_config_servicenet(lc):
    """
    Validate that if CLBs are provided, ServiceNet is also provided.
    """
    clb = any([lb.get('type', 'CloudLoadBalancer') == 'CloudLoadBalancer'
               for lb in get_in(('args', 'loadBalancers'), lc, default=())])
    networks = get_in(('args', 'server', 'networks'), lc, default=None)

    if (clb and
            networks is not None and
            {'uuid': '11111111-1111-1111-1111-111111111111'} not in networks):
        raise ValidationError("ServiceNet network must be present if one or "
                              "more Cloud Load Balancers are configured.")


# Datetime validator. Allow only zulu-based UTC timestamp
@format_checker.checks('date-time', raises=ValueError)
def validate_datetime(dt_str):
    """
    Validate date-time string in json. Return True if valid and raise
    ValueError if invalid
    """
    if dt_str and dt_str[-1] != 'Z':
        raise ValueError('Expecting Zulu-format UTC time')
    try:
        ep = timestamp_to_epoch(dt_str)
    except ParseError:
        raise ValueError('Error parsing datetime str')
    # Ensure time is in future - can't just parse into a datetime and compare
    # because we cannot compare naive datetimes with timezone-aware datetimes
    if datetime.utcfromtimestamp(ep) <= datetime.utcnow():
        raise ValidationError(
            'Invalid "{0}" datetime: It must be in the future'.format(dt_str))
    return True


# Register cron format checker with the global checker. Also, ensure it does not have seconds arg
@format_checker.checks('cron', raises=ValueError)
def validate_cron(cron):
    """
    Validate cron string in json. Return True if valid and raise ValueError if invalid
    """
    try:
        croniter(cron)
    except:
        # It is checking for any exception since croniter throws KeyError with some invalid inputs.
        # This issue has been raised in https://github.com/taichino/croniter/issues/25.
        # Following 2 issues are filed w.r.t AUTO-407:
        # https://github.com/taichino/croniter/issues/24 and
        # https://github.com/taichino/croniter/issues/23
        raise ValueError('Error parsing cron')
    if len(cron.split()) == 6:
        raise ValidationError('Invalid "{}" cron entry: Seconds not allowed'.format(cron))
    return True

_policy_base_type = {
    "type": "object",
    "properties": {
        "name": {},
        "cooldown": {},
    },
    "additionalProperties": False
}

# Couldn't add "there MUST be 'args' when type is schedule" rule in the schema
# Hence, this dirty hack: It creates all possible types
_policy_types = []
for change in ['change', 'changePercent', 'desiredCapacity']:
    for _type in ['schedule', 'webhook', 'cloud_monitoring']:
        _policy_type = deepcopy(_policy_base_type)
        _policy_type['properties'][change] = {'required': True}
        _policy_type['properties']['type'] = {'pattern': _type}
        if _type == 'schedule' or _type == 'cloud_monitoring':
            _policy_type['properties']['args'] = {'required': True}
        _policy_types.append(_policy_type)

policy = {
    "type": _policy_types,
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
                "does not affect the global scaling group cooldown.  Min is 0 "
                "seconds, max is 86400 seconds (24 hrs * 60 min * 60 sec)."),
            "minimum": 0,
            "maximum": MAX_COOLDOWN,
            "required": True
        },
        "type": {
            "enum": ["webhook", "schedule", "cloud_monitoring"],
            "required": True
        },
        "args": {
            "type": [
                {
                    "type": "object",
                    "properties": {"at": {"required": True}},
                    "additionalProperties": False
                },
                {
                    "type": "object",
                    "properties": {"cron": {"required": True}},
                    "additionalProperties": False
                },
                {
                    "type": "object",
                    "properties": {"alarm_criteria": {"required": True},
                                   "check": {"required": True}},
                    "additionalProperties": False
                }
            ],
            "properties": {
                "cron": {
                    "type": "string",
                    "description": (
                        "The recurrence pattern as a cron entry. This describes at what times"
                        "in the future will the scaling policy get executed. For example, if this is"
                        "'1 0 * * *' then the policy will get executed at one minute past midnight"
                        "(00:01) of every day of the month, of every day of the week."
                        "Kindly check http://en.wikipedia.org/wiki/Cron"),
                    "format": "cron"
                },
                "at": {
                    "type": "string",
                    "description": (
                        "The time at which this policy will be executed. This property is mutually"
                        "exclusive w.r.t 'cron'. Either 'cron' or 'at' can be given. Not both."),
                    "format": "date-time"
                }
            }
        }
    },
    "dependencies": {
        "args": {
            # args can be there only when type is 'schedule' or 'cloud_monitoring'
            "type": "object",
            "properties": {
                "type": {"enum": ["schedule", "cloud_monitoring"]}
            }
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

update_webhook = deepcopy(webhook)
update_webhook['properties']['metadata']['required'] = True
