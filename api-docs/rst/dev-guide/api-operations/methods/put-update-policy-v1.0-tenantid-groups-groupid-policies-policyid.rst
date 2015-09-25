
.. _put-update-policy-v1.0-tenantid-groups-groupid-policies-policyid:

Update scaling policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    PUT /v1.0/{tenantId}/groups/{groupId}/policies/{policyId}

This operation updates an existing scaling policy for the specified tenant.

To update the policy, specify the name, type, adjustment, and cooldown time for the policy in the request body in JSON format. If the change succeeds, no response body is returned.

.. note::
   All Rackspace Auto Scale update (**PUT**) operations completely replace the configuration being updated. Empty values (for example, { } )in the update are accepted and overwrite previously specified parameters. New parameters can be specified. All create (**POST**) parameters, even optional ones, are required for the update operation. 
   
   



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|204                       |Success But No Content   |The update scaling       |
|                          |                         |policy request succeeded.|
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidJsonError         |The request is refused   |
|                          |                         |because the body was     |
|                          |                         |invalid JSON".           |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |Both "at" and "cron"     |
|                          |                         |values for the "args"    |
|                          |                         |parameter are supplied.  |
|                          |                         |Only one such value is   |
|                          |                         |allowed.                 |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |More than one of         |
|                          |                         |"change" or              |
|                          |                         |"changePercent" or       |
|                          |                         |"desiredCapacity" values |
|                          |                         |are supplied. Only one   |
|                          |                         |such value is allowed.   |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |Neither "at" or "cron"   |
|                          |                         |values for the "args"    |
|                          |                         |parameter are supplied   |
|                          |                         |and this is a "schedule" |
|                          |                         |type policy.             |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |Neither "change" or      |
|                          |                         |"changePercent" or       |
|                          |                         |"desiredCapacity" values |
|                          |                         |are supplied.            |
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |The "args" parameter is  |
|                          |                         |not supplied and this is |
|                          |                         |a "schedule" type policy.|
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |The "at" value does not  |
|                          |                         |correspond to "YYYY-MM-  |
|                          |                         |DDTHH:MM:SS.SSSS" format.|
+--------------------------+-------------------------+-------------------------+
|400                       |ValidationError          |The "cron" value is      |
|                          |                         |invalid. It either       |
|                          |                         |contains a seconds       |
|                          |                         |component or is invalid  |
|                          |                         |cron expression.         |
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
|{policyId}                |Uuid *(Required)*        |A scaling policy.        |
+--------------------------+-------------------------+-------------------------+





This table shows the body parameters for the request:

+----------------------------+-------------+-------------------------------------------+
|Name                        |Type         |Description                                |
+============================+=============+===========================================+
|scalingPolicies.[*].\       |String       |A name for the scaling policy. This name   |
|**name**                    |*(Required)* |must be unique for each scaling policy.    |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Object       |Additional configuration information for   |
|**args**                    |*(Optional)* |policies of type "schedule." This          |
|                            |             |parameter is not required for policies of  |
|                            |             |type ``webhook``. This parameter must be   |
|                            |             |set to either ``at`` or ``cron``, which    |
|                            |             |are mutually exclusive.                    |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].args.\  |String       |The time when the policy runs, as a cron   |
|**cron**                    |*(Optional)* |entry. For example, if you set this        |
|                            |             |parameter to ``1 0 * * *``, the policy     |
|                            |             |runs at one minute past midnight (00:01)   |
|                            |             |every day of the month, and every day of   |
|                            |             |the week. For more information about cron, |
|                            |             |see `http://en.wikipedia.org/wiki/Cron     |
|                            |             |<http://en.wikipedia.org/wiki/Cron>`.      |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].args.\  |String       |The time when this policy will be          |
|**at**                      |*(Optional)* |executed. The time must be formatted       |
|                            |             |according to this service's custom :ref:   |
|                            |             |`Date and Time format <date-time-format>`, |
|                            |             |with seconds, otherwise a 400 error may be |
|                            |             |returned. The policy will be triggered     |
|                            |             |within a 10-second range of the time       |
|                            |             |specified, so if you set the``at`` time    |
|                            |             |to``2013-05-19T08:07:08Z``, it will be     |
|                            |             |triggered anytime between 08:07:08 to      |
|                            |             |08:07:18. This property is mutually        |
|                            |             |exclusive with the ``cron`` parameter.     |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Number       |The percent change to make in the number   |
|**changePercent**           |*(Optional)* |of servers in the scaling group. If this   |
|                            |             |number is positive, the number of servers  |
|                            |             |increases by the given percentage. If this |
|                            |             |parameter is set to a negative number, the |
|                            |             |number of servers decreases by the given   |
|                            |             |percentage. The absolute change in the     |
|                            |             |number of servers is rounded to the        |
|                            |             |nearest integer. This means that if -X% of |
|                            |             |the current number of servers translates   |
|                            |             |to -0.5 or -0.25 or -0.75 servers, the     |
|                            |             |actual number of servers that are shut     |
|                            |             |down is 1. If X% of the current number of  |
|                            |             |servers translates to 1.2 or 1.5 or 1.7    |
|                            |             |servers, the actual number of servers that |
|                            |             |are launched is 2.                         |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Number       |The cooldown period, in seconds, before    |
|**cooldown**                |*(Required)* |this particular scaling policy can run     |
|                            |             |again. The policy cooldown period does not |
|                            |             |affect the global scaling group cooldown.  |
|                            |             |The minimum value for this parameter is 0  |
|                            |             |seconds. The maximum value is 86400        |
|                            |             |seconds (24 hrs).                          |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Enum         |The type of policy that runs. Currently,   |
|**type**                    |*(Required)* |this value can be either ``webhook`` or    |
|                            |             |``schedule``.                              |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Integer      |The change to make in the number of        |
|**change**                  |*(Optional)* |servers in the scaling group. This         |
|                            |             |parameter must be an integer. If the value |
|                            |             |is a positive integer, the number of       |
|                            |             |servers increases. If the value is a       |
|                            |             |negative integer, the number of servers    |
|                            |             |decreases.                                 |
+----------------------------+-------------+-------------------------------------------+
|scalingPolicies.[*].\       |Integer      |The desired server capacity of the scaling |
|**desiredCapacity**         |*(Optional)* |the group; that is, how many servers       |
|                            |             |should be in the scaling group. This value |
|                            |             |must be an absolute number, greater than   |
|                            |             |or equal to zero. For example, if this     |
|                            |             |parameter is set to ten, executing the     |
|                            |             |policy brings the number of servers to     |
|                            |             |ten. The minimum allowed value is zero.    |
|                            |             |Note that the configured group maxEntities |
|                            |             |and minEntities takes precedence over this |
|                            |             |setting.                                   |
+----------------------------+-------------+-------------------------------------------+





**Example Update policy: JSON request**


.. code::

   {
      "change":1,
      "cooldown":1800,
      "name":"scale up by one server",
      "type":"webhook"
   }





Response
""""""""""""""""






This operation does not return a response body.




