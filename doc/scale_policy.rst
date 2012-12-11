====================
Scale Policy Schema
====================

**Document type: scale_up_policy**::

    {
        "name": "scale up by one server",
        "type" : "scale_up",
        "adjustment": 1,
        "cooldown": 150
    }

**Document type: scale_up_by_percent_policy**::

    {
        "name": "scale up one percent",
        "type" : "scale_up_percent",
        "adjustment": 10,
        "cooldown": 150
    }

**Document type: scale_down_policy**::

    {
        "name": "scale down one server",
        "type" : "scale_down",
        "adjustment": 1,
        "cooldown": 150
    }

**Document type: scale_down_by_percent_policy**::

    {
        "name": "scale down one percent",
        "type" : "scale_down_percent",
        "adjustment": 10,
        "cooldown": 150
    }