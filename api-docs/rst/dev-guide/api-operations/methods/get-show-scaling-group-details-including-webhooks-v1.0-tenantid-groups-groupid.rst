

.. _get-show-scaling-group-details-including-webhooks-v1.0-tenantid-groups-groupid:

Show scaling group details including webhooks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    GET /v1.0/{tenantId}/groups/{groupId}

This operation retrieves configuration details for a specified scaling group and its associated webhooks.

Details include the launch configuration, the scaling policies, and the policies' webhooks for the specified scaling group configuration.

The details appear in the response body in JSON format.

.. note::

    The ``?webhooks=true`` parameter is required for this method.


This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|200                       |OK                       |The request succeeded    |
|                          |                         |and the response         |
|                          |                         |contains details about   |
|                          |                         |the specified scaling    |
|                          |                         |group, including         |
|                          |                         |associated webhooks.     |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidQueryArgument     |The "limit" query        |
|                          |                         |argument value is not a  |
|                          |                         |valid integer.           |
+--------------------------+-------------------------+-------------------------+
|401                       |InvalidCredentials       |The X-Auth-Token the     |
|                          |                         |user supplied is bad.    |
+--------------------------+-------------------------+-------------------------+
|403                       |Forbidden                |The user does not have   |
|                          |                         |permission to perform    |
|                          |                         |the resource; for        |
|                          |                         |example, the user only   |
|                          |                         |has an observer role and |
|                          |                         |attempted to perform     |
|                          |                         |something only available |
|                          |                         |to a user with an admin  |
|                          |                         |role. Note, some API     |
|                          |                         |nodes also use this      |
|                          |                         |status code for other    |
|                          |                         |things.                  |
+--------------------------+-------------------------+-------------------------+
|404                       |NoSuchScalingGroupError  |The specified scaling    |
|                          |                         |group was not found.     |
+--------------------------+-------------------------+-------------------------+
|405                       |InvalidMethod            |The method used is       |
|                          |                         |unavailable for the      |
|                          |                         |endpoint.                |
+--------------------------+-------------------------+-------------------------+
|413                       |RateLimitError           |The user has surpassed   |
|                          |                         |their rate limit.        |
+--------------------------+-------------------------+-------------------------+
|500                       |InternalError            |An error internal to the |
|                          |                         |application has          |
|                          |                         |occurred, please file a  |
|                          |                         |bug report.              |
+--------------------------+-------------------------+-------------------------+
|503                       |ServiceUnavailable       |The requested service is |
|                          |                         |unavailable, please file |
|                          |                         |a bug report.            |
+--------------------------+-------------------------+-------------------------+


Request
""""""""""""""""




This table shows the URI parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|{tenantId}                |String *(Required)*      |A subscriber to the auto |
|                          |                         |scaling service.         |
+--------------------------+-------------------------+-------------------------+
|X-Auth-Token              |String *(Required)*      |A valid authentication   |
|                          |                         |token.                   |
+--------------------------+-------------------------+-------------------------+
|{groupId}                 |Uuid *(Required)*        |A scaling group.         |
+--------------------------+-------------------------+-------------------------+



This table shows the query parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|webhooks                  |Boolean *(Required)*     |Set ``?webhooks=true``   |
|                          |                         |to display webhook       |
|                          |                         |configuration details in |
|                          |                         |the results.             |
+--------------------------+-------------------------+-------------------------+




This operation does not accept a request body.




Response
""""""""""""""""










**Example Show scaling group details including webhooks: JSON response**


.. code::

   {
     "group": {
       "groupConfiguration": {
         "cooldown": 60,
         "maxEntities": 0,
         "metadata": {},
         "minEntities": 0,
         "name": "smallest possible launch config group"
       },
       "state": {
         "active": [],
         "activeCapacity": 0,
         "desiredCapacity": 0,
         "paused": false,
         "pendingCapacity": 0
       },
       "id": "605e13f6-1452-4588-b5da-ac6bb468c5bf",
       "launchConfiguration": {
         "args": {
           "server": {}
         },
         "type": "launch_server"
       },
       "links": [
         {
           "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/",
           "rel": "self"
         }
       ],
       "scalingPolicies": [
         {
           "changePercent": -5.5,
           "cooldown": 1800,
           "id": "eb0fe1bf-3428-4f34-afd9-a5ac36f60511",
           "links": [
             {
               "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/eb0fe1bf-3428-4f34-afd9-a5ac36f60511/",
                   "rel": "self"
               }
           ],
           "name": "scale down by 5.5 percent",
           "type": "webhook",
           "webhooks": [
             {
               "id":"05f7d9d9-b9d0-40ac-8d3b-610197775c7f",
               "name": "automatically generated",
               "metadata": {},
               "links": [
                 {
                   "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/eb0fe1bf-3428-4f34-afd9-a5ac36f60511/webhooks/05f7d9d9-b9d0-40ac-8d3b-610197775c7f/",
                   "rel": "self"
                 },
                 {
                   "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/execute/1/392be67bacfd1adf54e4f9fbc2b40873b9c7c3128315647f46d94c4b5c56b4d6/",
                   "rel": "capability"
                 }
               ]
             }
           ],
           "webhooks_links": [
             {
               "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/eb0fe1bf-3428-4f34-afd9-a5ac36f60511/webhooks/",
               "rel": "webhooks"
             }
           ]
         }
       ],
       "scalingPolicies_links": [
         {
           "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/",
           "rel": "policies"
         }
       ]
     }
   }
