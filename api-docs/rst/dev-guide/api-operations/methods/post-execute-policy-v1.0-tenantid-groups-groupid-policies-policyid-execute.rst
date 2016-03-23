
.. _execute-policy:

Execute policy
^^^^^^^^^^^^^^

.. code::

    POST /v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/execute

This operation runs a specified scaling policy.

If the operation succeeds, a response body is returned.

This table shows the possible response codes for this operation:

+--------------------------+-------------------------+------------------------------+
|Response Code             |Name                     |Description                   |
+==========================+=========================+==============================+
|202                       |Accepted                 |The execute policy            |
|                          |                         |request was accepted.         |
|                          |                         |The actual execution may      |
|                          |                         |be delayed, but will be       |
|                          |                         |attempted if no errors        |
|                          |                         |are returned. Use the         |
|                          |                         |"GET scaling group            |
|                          |                         |state" method to see if       |
|                          |                         |the policy was executed.      |
+--------------------------+-------------------------+------------------------------+
|400                       |InvalidJsonError         |The request is refused        |
|                          |                         |because the body was          |
|                          |                         |invalid JSON".                |
+--------------------------+-------------------------+------------------------------+
|400                       |ValidationError          |The request body had          |
|                          |                         |valid JSON but with           |
|                          |                         |unexpected properties or      |
|                          |                         |values in it. There can       |
|                          |                         |be many combinations that     |
|                          |                         |can cause this error.         |
+--------------------------+-------------------------+------------------------------+
|401                       |InvalidCredentials       |The X-Auth-Token the          |
|                          |                         |user supplied is bad.         |
+--------------------------+-------------------------+------------------------------+
|403                       |CannotExecutePolicyError |The policy did not            |
|                          |                         |run because a                 |
|                          |                         |scaling policy or             |
|                          |                         |scaling group cooldown        |
|                          |                         |was still in effect.          |
+--------------------------+-------------------------+------------------------------+
|403                       |CannotExecutePolicyError |The policy did not            |
|                          |                         |run because                   |
|                          |                         |applying the changes          |
|                          |                         |would not result in the       |
|                          |                         |addition or deletion of       |
|                          |                         |any servers.                  |
+--------------------------+-------------------------+------------------------------+
|403                       |GroupPausedError         |The policy did not run        |
|                          |                         |because the group is          |
|                          |                         |paused. You can resolve       |
|                          |                         |this error by                 |
|                          |                         |:ref:`resuming <resume-group>`|
|                          |                         |the group.                    |
+--------------------------+-------------------------+------------------------------+
|403                       |Forbidden                |The user does not have        |
|                          |                         |permission to perform         |
|                          |                         |the resource; for             |
|                          |                         |example, the user only        |
|                          |                         |has an observer role and      |
|                          |                         |attempted to perform          |
|                          |                         |something only available      |
|                          |                         |to a user with an admin       |
|                          |                         |role. Note, some API          |
|                          |                         |nodes also use this           |
|                          |                         |status code for other         |
|                          |                         |things.                       |
+--------------------------+-------------------------+------------------------------+
|404                       |NoSuchPolicyError        |The requested scaling         |
|                          |                         |policy was not found in       |
|                          |                         |the specified scalilng        |
|                          |                         |group.                        |
+--------------------------+-------------------------+------------------------------+
|404                       |NoSuchScalingGroupError  |The specified scaling         |
|                          |                         |group was not found.          |
+--------------------------+-------------------------+------------------------------+
|405                       |InvalidMethod            |The method used is            |
|                          |                         |unavailable for the           |
|                          |                         |endpoint.                     |
+--------------------------+-------------------------+------------------------------+
|413                       |RateLimitError           |The user has surpassed        |
|                          |                         |their rate limit.             |
+--------------------------+-------------------------+------------------------------+
|415                       |UnsupportedMediaType     |The request is refused        |
|                          |                         |because the content type      |
|                          |                         |of the request is not         |
|                          |                         |"application/json".           |
+--------------------------+-------------------------+------------------------------+
|500                       |InternalError            |An error internal to the      |
|                          |                         |application has               |
|                          |                         |occurred, please file a       |
|                          |                         |bug report.                   |
+--------------------------+-------------------------+------------------------------+
|503                       |ServiceUnavailable       |The requested service is      |
|                          |                         |unavailable, please file      |
|                          |                         |a bug report.                 |
+--------------------------+-------------------------+------------------------------+


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

This operation does not accept a request body.

Response
""""""""""""""""

This operation does not return a response body.
