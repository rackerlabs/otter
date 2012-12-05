====================
Launch Config Schema
====================

**Document type: launch_server**::

The server arg contains arguments that will be passed to nova's create server API.  It is treated as opaque to autoscale.  (Nova should handle validation).

    {
        "type": "launch_servers",
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
            "loadBalancers":
                {
                    "id": 500,
                    "port": 80
                }
            ]
        }
    }
