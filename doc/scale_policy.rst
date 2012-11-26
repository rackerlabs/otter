====================
Scale Policy Schema
====================

**Document type: scale_up_policy**::

    {
        "scale_policy_name": "...",
        "scaling_group": "...",
        "launch_policy": "...",
        "type" : "scale_up",
        "adjustment": "1",
        "cooldown": "150"
    }

**Document type: scale_up_by_percent_policy**::

    {
        "scale_policy_name": "...",
        "scaling_group": "...",
        "launch_policy": "...",
        "type" : "scale_up_percent",
        "adjustment": "10",
        "cooldown": "150"
    }

**Document type: scale_down_policy**::

    {
        "scale_policy_name": "...",
        "scaling_group": "...",
        "launch_policy": "...",
        "type" : "scale_down",
        "adjustment": "1",
        "cooldown": "150"
    }

**Document type: scale_down_by_percent_policy**::

    {
        "scale_policy_name": "...",
        "scaling_group": "...",
        "launch_policy": "...",
        "type" : "scale_down_percent",
        "adjustment": "10",
        "cooldown": "150"
    }