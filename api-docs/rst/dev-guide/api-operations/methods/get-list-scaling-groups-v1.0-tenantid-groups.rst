

.. _get-list-scaling-groups-v1.0-tenantid-groups:

List scaling groups
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    GET /v1.0/{tenantId}/groups

This operation lists the scaling groups that are available for a specified tenant.



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|200                       |OK                       |The request succeeded    |
|                          |                         |and the response         |
|                          |                         |contains the list of     |
|                          |                         |scaling groups.          |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidQueryArgument     |The "limit" query        |
|                          |                         |argument is not a valid  |
|                          |                         |integer.                 |
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





This operation does not accept a request body.




Response
""""""""""""""""










**Example List scaling groups: JSON response**


.. code::

   {
      "groups":[
         {
            "id":"e41380ae-173c-4b40-848a-25c16d7fa83d",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/e41380ae-173c-4b40-848a-25c16d7fa83d/",
                  "rel":"self"
               }
            ],
            "state":{
               "active":[
   
               ],
               "activeCapacity":0,
               "desiredCapacity":0,
               "paused":false,
               "pendingCapacity":0,
               "name":"testscalinggroup198547"
            }
         },
         {
            "id":"f82bb000-f451-40c8-9dc3-6919097d2f7e",
            "state":{
               "active":[
   
               ],
               "activeCapacity":0,
               "desiredCapacity":0,
               "paused":false,
               "pendingCapacity":0,
               "name":"testscalinggroup198547"
            },
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/f82bb000-f451-40c8-9dc3-6919097d2f7e/",
                  "rel":"self"
               }
            ]
         }
      ],
      "groups_links":[
   
      ]
   }




