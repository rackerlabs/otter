"""
Methods to get valid examples of config setup data, as specified those in
`otter.json_schema.group_schemas`.  This is to be used for testing and for
documentation.

These are methods, instead of just definitions, so that in testing there need
not be any worry of mutating the defitions.
"""


def launch_server_config():
    """
    Return an array of valid launch config examples
    """
    return [
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "3",
                    "name": "webhead",
                    "imageRef": "0d589460-f177-4b0f-81c1-8ab8903ac7d8",
                    "OS-DCF:diskConfig": "AUTO",
                    "metadata": {
                        "mykey": "myvalue"
                    },
                    "personality": [
                        {
                            "path": '/root/.ssh/authorized_keys',
                            "contents": (
                                "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp")
                        }
                    ],
                    "networks": [
                        {
                            "uuid": "11111111-1111-1111-1111-111111111111"
                        }
                    ],
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": 2200,
                        "port": 8081
                    }
                ],
                "draining_timeout": 30
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": 441,
                        "port": 80
                    },
                    {
                        "loadBalancerId": 2200,
                        "port": 8081
                    }
                ]
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2",
                        "type": "RackConnectV3"
                    }
                ]
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": 2200,
                        "port": 8081,
                        "type": "CloudLoadBalancer"
                    }
                ]
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": "2200",
                        "port": 8081,
                        "type": "CloudLoadBalancer"
                    }
                ]
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": "441",
                        "port": 80
                    }
                ]
            }
        },
        {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": "2",
                    "name": "worker",
                    "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0",
                    "personality": [
                        {
                            "path": "/etc/banner.txt",
                            "contents": "VGhpcyBpcyBhIHRlc3Qgb2YgYmFzZTY0IGVuY29kaW5n"
                        }
                    ]
                }
            }
        }
    ]


def launch_stack_config():
    """
    Return an array of valid launch config examples.
    """
    def get_stack_config(request_body):
        """
        Takes a stack create request body and returns a launch_stack config.
        """
        return {
            "type": "launch_stack",
            "args": {
                "stack": request_body
            }
        }

    json_template = {
        "heat_template_version": "2015-04-30",
        "resources": {
            "rand": {"type": "OS::Heat::RandomString"}
        }
    }

    yaml_template = "\n".join([
        "heat_template_version: 2015-04-30",
        "resources:",
        "  rand:",
        "    type: OS::Heat::RandomString"
    ])

    json_environment = {
        "parameters": {
            "foo": "bar"
        },
        "resource_registry": {
            "Heat::Foo": "https://foo.bar/baz.yaml"
        }
    }

    yaml_environment = "\n".join([
        "parameters:",
        "  foo: bar",
        "resource_registry:",
        "  Heat::Foo: https://foo.bar/baz.yaml"
    ])

    stack_req_bodies = {
        "minimal_with_url": {
            "template_url": "https://foo.bar/baz.template"
        },
        "mimimal_with_json_template": {
            "template": json_template
        },
        "mimimal_with_yaml_template": {
            "template": yaml_template
        },
        "all_options": {
            "template": json_template,
            "disable_rollback": True,
            "environment": json_environment,
            "files": {
                "fileA.yaml": "A contents",
                "file:///usr/fileB.template": "B contents",
                "http://example.com/fileC.template": "C contents"
            },
            "parameters": {
                "string": "foo",
                "number": 3.14159,
                "json": {"foo": "bar", "baz": "quux"},
                "list": ["comma", "delimited", "list"],
                "boolean": True
            },
            "timeout_mins": 60
        },
        "mimimal_with_json_environment": {
            "template": yaml_template,
            "environment": json_environment
        },
        "mimimal_with_yaml_environment": {
            "template": yaml_template,
            "environment": yaml_environment
        },
    }

    return {k: get_stack_config(body) for k, body in stack_req_bodies.items()}


def config():
    """
    Return an array of valid scaling group examples
    """
    return [
        {
            "name": "webheads",
            "cooldown": 30,
            "minEntities": 1
        },
        {
            "name": "workers",
            "cooldown": 60,
            "minEntities": 5,
            "maxEntities": 20,
            "metadata": {
                "firstkey": "this is a string",
                "secondkey": "1"
            }
        }
    ]


def policy():
    """
    Return an array of valid scaling policy examples
    """
    return [
        {
            "name": "scale up by 10",
            "change": 10,
            "cooldown": 5,
            "type": "webhook"
        },
        {
            "name": 'scale down by 5.5 percent',
            "changePercent": -5.5,
            "cooldown": 6,
            "type": "webhook"
        },
        {
            "name": 'set number of servers to 10',
            "desiredCapacity": 10,
            "cooldown": 3,
            "type": "webhook"
        },
        {
            "name": "Schedule policy to run at May 20 2015",
            "cooldown": 3,
            "changePercent": -5.5,
            "type": "schedule",
            "args": {
                "at": "2050-05-20T00:00:00Z"
            }
        },
        {
            "name": "Schedule policy to run repeately",
            "cooldown": 3,
            "change": 10,
            "type": "schedule",
            "args": {
                "cron": "0 */2 * * *"
            }
        }
    ]
