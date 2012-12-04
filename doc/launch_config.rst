====================
Launch Config Schema
====================

**Document type: launch_server**::

    {
        "imageId": "image_uuid_string",
        "flavorId": "...",
        "networks": [
            "..."
        ],
        "loadBalancers": [
            {
                id: "",
                port: ""
            }
        ],
        "volumes": [
            {
                "volumeId": "...",
                "device": "..."
            },
            {
                "volumeId": "...",
                "device": "..."
            }
        ],
        "metadata": {},
    }
