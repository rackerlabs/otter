

.. _put-update-webhook-v1.0-tenantid-groups-groupid-policies-policyid-webhooks-webhookid:

Update webhook
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    PUT /v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks/{webhookId}

This operation updates a webhook for a specified tenant and scaling policy.

If the specified webhook is not recognized, the change is ignored. If you submit a URL, the URL is ignored but that does not invalidate the request. If the change is successful, no response body is returned.

.. note::
   All Rackspace Auto Scale update (**PUT**) operations completely replace the configuration being updated. Empty values (for example, { } )in the update are accepted and overwrite previously specified parameters. New parameters can be specified. All create (**POST**) webhook parameters, even optional ones, are required for the update webhook operation, including the ``metadata`` parameter. 
   
   



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|204                       |Success But No Content   |The update webhook       |
|                          |                         |request succeeded.       |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidJsonError         |A syntax or parameter    |
|                          |                         |error. The create        |
|                          |                         |webhook request body had |
|                          |                         |invalid JSON.            |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidJsonError         |The request is refused   |
|                          |                         |because the body was     |
|                          |                         |invalid JSON".           |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |A syntax or parameter    |
|                          |                         |error. The create        |
|                          |                         |webhook request body had |
|                          |                         |bad.                     |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |The request body had     |
|                          |                         |valid JSON but with      |
|                          |                         |unexpected properties or |
|                          |                         |values in it. Please     |
|                          |                         |note that there can be   |
|                          |                         |many combinations that   |
|                          |                         |cause this error.        |                       
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
|415                       |UnsupportedMediaType     |The request is refused   |
|                          |                         |because the content type |
|                          |                         |of the request is not    |
|                          |                         |"application/json".      |
+--------------------------+-------------------------+-------------------------+
|422                       |WebhookOverLimitsError   |The user has reached     |
|                          |                         |their quota for          |
|                          |                         |webhooks, currently 25.  |
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





This table shows the body parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|[*].\ **name**            |String *(Required)*      |A name for the webhook   |
|                          |                         |for logging purposes.    |
+--------------------------+-------------------------+-------------------------+
|[*].\ **metadata**        |Object *(Optional)*      |User-provided key-value  |
|                          |                         |metadata. Both keys and  |
|                          |                         |values should be strings |
|                          |                         |not exceeding 256        |
|                          |                         |characters in length.    |
+--------------------------+-------------------------+-------------------------+





**Example Update webhook: JSON request**


.. code::

   {
       "name": "alice",
       "metadata": {
           "notes": "this is for Alice"
       }
   }





Response
""""""""""""""""






This operation does not return a response body.




