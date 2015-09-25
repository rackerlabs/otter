
.. _delete-delete-scaling-group-v1.0-tenantid-groups-groupid:

Delete scaling group
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    DELETE /v1.0/{tenantId}/groups/{groupId}

This operation deletes a specified scaling group.

The scaling group must be empty before it can be deleted. An empty group contains no entities. If deletion is successful, no response body is returned. If the group contains pending or active entities, deletion fails and a 409 error message is returned. If there are pending or active servers in the scaling group, pass ``force=true`` to force delete the group. Passing ``force=true`` immediately deletes all active servers in the group. Pending servers are deleted when they build and become active.



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|204                       |Success But No Content   |The delete scaling group |
|                          |                         |request succeeded.       |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidQueryArgument     |The "force" query        |
|                          |                         |argument value is        |
|                          |                         |invalid. It must be      |
|                          |                         |"true", any other value  |
|                          |                         |is invalid. If there are |
|                          |                         |servers in the group,    |
|                          |                         |only "true" succeeds. If |
|                          |                         |there are no servers in  |
|                          |                         |the group, "true" and no |
|                          |                         |value given succeed.     |
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
|403                       |GroupNotEmptyError       |The scaling group cannot |
|                          |                         |be deleted because it    |
|                          |                         |has servers in it. Use   |
|                          |                         |the "force=true" query   |
|                          |                         |argument to force delete |
|                          |                         |the group.               |
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






This operation does not return a response body.




