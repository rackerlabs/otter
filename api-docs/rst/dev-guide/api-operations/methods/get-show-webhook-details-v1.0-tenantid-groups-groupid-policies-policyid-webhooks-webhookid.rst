

.. _get-show-webhook-details-v1.0-tenantid-groups-groupid-policies-policyid-webhooks-webhookid:

Show webhook details
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    GET /v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks/{webhookId}

This operation retrieves webhook details for a specified scaling policy.

The details appear in the response body in JSON format.


This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|200                       |OK                       |The request succeeded    |
|                          |                         |and the response         |
|                          |                         |contains details about   |
|                          |                         |the specified webhook.   |
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
|404                       |NoSuchPolicyError        |The requested scaling    |
|                          |                         |policy was not found in  |
|                          |                         |the specified scaling    |
|                          |                         |group.                   |
+--------------------------+-------------------------+-------------------------+
|404                       |NoSuchScalingGroupError  |The specified scaling    |
|                          |                         |group was not found.     |
+--------------------------+-------------------------+-------------------------+
|404                       |NoSuchWebhookError       |The specified webhook    |
|                          |                         |was not found.           |
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
|{policyId}                |Uuid *(Required)*        |A scaling policy.        |
+--------------------------+-------------------------+-------------------------+
|{webhookId}               |Uuid *(Required)*        |A webhook.               |
+--------------------------+-------------------------+-------------------------+





This operation does not accept a request body.




Response
""""""""""""""""


**Example Show webhook details: JSON response**


.. code::

   
   
   {
      "webhook":{
         "id":"23037efb-53a9-4ae5-bc33-e89a56b501b6",
         "links":[
            {
               "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/eb0fe1bf-3428-4f34-afd9-a5ac36f60511/webhooks/23037efb-53a9-4ae5-bc33-e89a56b501b6/",
               "rel":"self"
            },
            {
               "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/execute/1/4f767340574433927a26dc747253dad643d5d13ec7b66b764dcbf719b32302b9/",
               "rel":"capability"
            }
         ],
         "metadata":{
   
         },
         "name":"Nagios"
      }
   }




