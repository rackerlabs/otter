=====================
Used Limits Extension
=====================

Extends limits to include information about the absolute limits that are
currently used. Returns absolute and rate limit information, including
information about the currently used absolute limits.

Absolute and rate limits are part of the core API. See :doc:`limits`. The used
limits extension adds attributes to the response body that show how much
capacity is currently being used.

In the following response example, the total RAMUsed value is an extended
attribute.

The following example response shows a JSON response.

**Example: Used Limits: JSON Response:**

.. code::

    {
     "limits": {
         "rate": [
         {
             "uri": "*",
                 "regex": ".*",
                 "limit": [
                 {
                     "value": 10,
                     "verb": "POST",
                     "remaining": 2,
                     "unit": "MINUTE",
                     "next-available": "2011-12-15T22:42:45Z"
                 },
                 {
                     "value": 10,
                     "verb": "PUT",
                     "remaining": 2,
                     "unit": "MINUTE",
                     "next-available": "2011-12-15T22:42:45Z"
                 },
                 {
                     "value": 100,
                     "verb": "DELETE",
                     "remaining": 100,
                     "unit": "MINUTE",
                     "next-available": "2011-12-15T22:42:45Z"
                 }
             ]
         },
         {
             "uri": "*changes-since*",
             "regex": "changes-since",
             "limit": [
             {
                 "value": 3,
                 "verb": "GET",
                 "remaining": 3,
                 "unit": "MINUTE",
                 "next-available": "2011-12-15T22:42:45Z"
             }
             ]
         },
         {
             "uri": "*/servers",
             "regex": "^/servers",
             "limit": [
             {
                 "verb": "POST",
                 "value": 25,
                 "remaining": 24,
                 "unit": "DAY",
                 "next-available": "2011-12-15T22:42:45Z"
             }
             ]
         }
         ],
             "absolute": {
                 "maxTotalRAMSize": 51200,
                 "totalRAMUsed": 1024,
                 "maxServerMeta": 5,
                 "maxImageMeta": 5,
                 "maxPersonality": 5,
                 "maxPersonalitySize": 10240
             }
     }
    }