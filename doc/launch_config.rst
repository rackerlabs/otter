====================
Launch Config Schema
====================

**Document type: launch_server**::

    {
        "type": "launch_servers",
        "args": {
            "server": {
                "...nova create server args..."
            },
            "loadBalancers":
                {
                    "id": "",
                    "port": "",
                    "network": ""
                }
            ]
        }
    }
