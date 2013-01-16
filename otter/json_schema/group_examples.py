"""
Valid examples of config setup data, as specified those in
`otter.json_schema.group_schemas`.  This is to be used for testing and for
documentation.
"""

# Valid launch config examples
launch_server_config = [
    {
        "type": "launch_server",
        "args": {
            "server": {
                "flavorRef": 3,
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
                "flavorRef": 2,
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
                "flavorRef": 2,
                "name": "worker",
                "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
            }
        }
    }
]


config = [
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
            "secondkey": "1"
        }
    }
]

policy = [
    {
        "name": "scale up by 10",
        "change": 10,
        "cooldown": 5
    },
    {
        "name": 'scale down a 5.5 percent because of a tweet',
        "changePercent": -5.5,
        "cooldown": 6
    },
    {
        "name": 'set number of servers to 10',
        "steadyState": 10,
        "cooldown": 3
    }
]
