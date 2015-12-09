

.. _post-create-scaling-group-v1.1-tenantid-converge:

Trigger convergence
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    POST /v1.1/{tenantId}/groups/groupId/converge

This operation triggers convergence for a specific scaling group. Convergence implies that Autoscale attempts to continuously converge to the desired state of the scaling group, instead of manipulating servers only once.
When the convergence process starts, it will continue until the desired number of servers are in the ACTIVE state.

If the request succeeds, the response body describes the created group in JSON format. The response includes an ID and links for the group.

If the operation succeeds, a 204 response code is returned.



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|204                       |Success                  |Convergence has been     |
|                          |                         |successfully triggered.  |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidJsonError         |The request is refused   |
|                          |                         |because the body was     |
|                          |                         |invalid JSON".           |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |The request body had     |
|                          |                         |valid JSON but with      |
|                          |                         |unexpected properties or |
|                          |                         |values in it. There can  |
|                          |                         |be many combinations that|
|                          |                         |can cause this error.    |
+--------------------------+-------------------------+-------------------------+
|401                       |InvalidCredentials       |The X-Auth-Token the     |
|                          |                         |user supplied is bad.    |
+--------------------------+-------------------------+-------------------------+
|403                       |GroupPausedError         |Convergence was not      |
|                          |                         |triggered because the    |
|                          |                         |group state is set to    |
|                          |                         |`"paused": true`.        |
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
|415                       |UnsupportedMediaType     |The request is refused   |
|                          |                         |because the content type |
|                          |                         |of the request is not    |
|                          |                         |"application/json".      |
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



This operation does not accept a request body.




Response
""""""""""""""""


This operation does not return a response body.
