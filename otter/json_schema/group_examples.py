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
                }
            }
        }
    ]


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
                "at": "2015-05-20T00:00:00Z"
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
