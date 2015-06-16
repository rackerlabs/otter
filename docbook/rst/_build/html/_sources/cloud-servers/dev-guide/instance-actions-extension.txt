==========================
Instance Actions Extension
==========================

The Instance Actions extension allows you to view a log of events and actions
taken on a server. First do a GET $endpoint/servers/{server-id}/os-instance-actions
to see a list of the actions, then you can show more details with GET
$endpoint/servers/{server-id}/os-instance-actions/{request-id}.

**Example: List Server Actions: JSON Response**

.. code::

   {
     "instanceActions": [
        {
           "action": "reboot",
           "instance_uuid": "86cf2416-aaa7-4579-a4d7-0bfe42bfa8ff",
           "message": null,
           "project_id": "453265",
           "request_id": "req-7b6f6a5e-daf7-483e-aea5-a11993d1d357",
           "start_time": "2013-08-15T21:40:42.000000",
           "user_id": "35746"
        },
        {
           "action": "create",
           "instance_uuid": "86cf2416-aaa7-4579-a4d7-0bfe42bfa8ff",
           "message": null,
           "project_id": "453265",
           "request_id": "req-920c6627-c8c9-4d02-9d3d-81917e5586df",
           "start_time": "2013-07-12T21:35:37.000000",
           "user_id": "35746"
        }
     ]
   }


**Example: Show Server Action: JSON**

.. code::

   {
     "instanceAction": {
        "action": "create",
        "instance_uuid": "86cf2416-aaa7-4579-a4d7-0bfe42bfa8ff",
        "message": null,
        "project_id": "453265",
        "request_id": "req-920c6627-c8c9-4d02-9d3d-81917e5586df",
        "start_time": "2013-07-12T21:35:37.000000",
        "user_id": "35746"
     }
   }
