====================
Launch Config Schema
====================

**Document type: launch_server**::

    {
        "scaling_group": "",
        "type" : "launch_server",
        "args": {
            "image": "...",
            "flavor": "...",
            "networks": [
                "..."
            ],
            "load_balancers": [
                {
                    id: "",
                    port: ""
                }
            ],
            "metadata": {},
            "volumes": [
                {
                    "snapshot_id": "...",
                    "volume_type": "...",
                    "size": "...",
                    "device": "..."
                },
                {
                    "snapshot_id": "...",
                    "volume_type": "...",
                    "size": "...",
                    "device": "..."
                }
            ]
        }
    }