

.. _get-group-state:

Get scaling group state
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    GET /v1.0/{tenantId}/groups/{groupId}/state

This operation retrieves the current state of a scaling group.

The *GroupState* object consists of the following properties:


*  *paused*. If ``paused=TRUE``, the group does not scale up or down. All
   scheduled or API-generated policy operations are suspended, and convergence
   is not triggered. When the group is paused, any POST requests to
   :ref:`converge <trigger-convergence>` or :ref:`execute policy <execute-policy>`
   operations return a ``403 GroupPausedError`` response.
   If ``paused=FALSE``, all group scaling and convergence operations resume and
   scheduled or API-generated policy exectuions are allowed.
*  *pendingCapacity*. Integer. Specifies the number of servers that are in a "building" state.
*  *name*. Specifies the name of the group.
*  *active*. Specifies an array of active servers in the group. This array includes the server Id, as well as other data.
*  *activeCapacity*. Integer. Specifies the number of active servers in the group.
*  *desiredCapacity*. Integer. Specifies the number of servers that are desired in the scaling group.
*  *status*. String. Indicates the scaling group status. If ``status=ACTIVE``,
   the scaling group is healthy and actively scaling up and down on request.
   If ``status=ERROR``, the scaling group cannot complete scaling operation
   requests successfully, typically due to an unrecoverable error that requires
   user attention.
*  *errors*. List of objects. If ``status=ERROR`` then this field contains
   a list of JSON objects with each object containing a message property
   that describes the error in human readable format.


This operation retrieves the current state of the specified scaling group. It describes the state of the group in terms of its current set of active entities, the number of pending entities, and the desired number of entities. The description is returned in the response body in JSON format.



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|200                       |OK                       |The request succeeded    |
|                          |                         |and the response         |
|                          |                         |describes the state of   |
|                          |                         |the specified scaling    |
|                          |                         |group.                   |
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



This operation does not accept a request body.



Response
""""""""""""""""



**Example Get scaling group state: JSON response with ACTIVE status**


.. code::

     {
        "group":{
           "paused":false,
           "pendingCapacity":0,
           "name":"testscalinggroup198547",
           "active":[],
           "activeCapacity":0,
           "desiredCapacity":0
           "status": "ACTIVE"
        }
     }


**Example Get scaling group state: JSON response with ERROR status**


.. code::

     {
        "group":{
          "paused":false,
          "pendingCapacity":0,
          "name":"testscalinggroup198547",
          "active":[],
          "activeCapacity":0,
          "desiredCapacity":0
          "status": "ERROR"
          "errors": [
            {"message": "Cloud load balancer 85621 is being deleted"}
         ]
       }
     }
