

.. _post-create-policy-v1.0-tenantid-groups-groupid-policies:

Create scaling policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    POST /v1.0/{tenantId}/groups/{groupId}/policies

This operation creates one or more scaling policies for a specified scaling group.

To create a policy, specify it in the request body in JSON format. Each description must include a name, type, adjustment, and cooldown time.

Use the JSON response to obtain information about the newly-created policy or policies:



*  The response header points to the List Policies endpoint.
*  The response body provides an array of scaling policies.


The examples that are provided below show several methods for creating a scaling policy:



*  A request to create a policy based on desired capacity.
*  A request to create a policy based on incremental change.
*  A request to create a policy based on change percentage.
*  A request to create a policy based on change percentage scheduled daily, at a specific time of day.
*  A request to create a policy based on change percentage scheduled once, for a specific date and time.
*  A request to create multiple policies, followed by the matching response.




This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|201                       |Created                  |The scaling policy has   |
|                          |                         |been created.            |
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
|                          |                         |cause this error. We     |
|                          |                         |will try to list the     |
|                          |                         |most common mistakes     |
|                          |                         |users are likely to make |
|                          |                         |in a particular request. |
|                          |                         |".                       |
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
|415                       |UnsupportedMediaType     |The request is refused   |
|                          |                         |because the content type |
|                          |                         |of the request is not    |
|                          |                         |"application/json".      |
+--------------------------+-------------------------+-------------------------+
|422                       |PoliciesOverLimitError   |The user has reached     |
|                          |                         |their quota for scaling  |
|                          |                         |policies, currently 100. |
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





This table shows the body parameters for the request:

+--------------------+-------------+-------------------------------------------+
|Name                |Type         |Description                                |
+====================+=============+===========================================+
|[*]                 |Array        |An array of scaling policies.              |
|                    |*(Required)* |                                           |
+--------------------+-------------+-------------------------------------------+
|[*].\ **args**      |Object       |Additional configuration information for   |
|                    |*(Optional)* |policies of type ``schedule``. This        |
|                    |             |parameter is not required for policies of  |
|                    |             |type ``webhook``. This parameter must be   |
|                    |             |set to either ``at`` or ``cron``, which    |
|                    |             |are mutually exclusive.                    |
+--------------------+-------------+-------------------------------------------+
|[*].args.\ **cron** |String       |The time when the policy will be executed, |
|                    |*(Optional)* |as a cron entry. For example, if this is   |
|                    |             |parameter is set to ``1 0 * * *``, the     |
|                    |             |policy will be executed at one minute past |
|                    |             |midnight (00:01) every day of the month,   |
|                    |             |and every day of the week. For more        |
|                    |             |information about cron, read:              |
|                    |             |http://en.wikipedia.org/wiki/Cron          |
+--------------------+-------------+-------------------------------------------+
|[*].args.\ **at**   |String       |The time when this policy will be          |
|                    |*(Optional)* |executed. The time must be formatted       |
|                    |             |according to this service's custom :ref:   |
|                    |             |`Date and Time format <date-time-format>`  |
|                    |             |with seconds, otherwise a 400 error may be |
|                    |             |returned. The policy will be triggered     |
|                    |             |within a 10-second range of the time       |
|                    |             |specified, so if you set the ``at`` time   |
|                    |             |to ``2013-05-19T08:07:08Z``, it will be    |
|                    |             |triggered anytime between 08:07:08 to      |
|                    |             |08:07:18. This property is mutually        |
|                    |             |exclusive with the ``cron`` parameter.     |
+--------------------+-------------+-------------------------------------------+
|[*].\               |Number       |The percent change to make in the number   |
|**changePercent**   |*(Optional)* |of servers in the scaling group. If this   |
|                    |             |number is positive, the number of servers  |
|                    |             |will increase by the given percentage. If  |
|                    |             |this parameter is set to a negative        |
|                    |             |number, the number of servers decreases by |
|                    |             |the given percentage. The absolute change  |
|                    |             |in the number of servers will be rounded   |
|                    |             |to the nearest integer. This means that if |
|                    |             |-X% of the current number of servers       |
|                    |             |translates to -0.5 or -0.25 or -0.75       |
|                    |             |servers, the actual number of servers that |
|                    |             |will be shut down is 1. If X% of the       |
|                    |             |current number of servers translates to    |
|                    |             |1.2 or 1.5 or 1.7 servers, the actual      |
|                    |             |number of servers that will be launched is |
|                    |             |2                                          |
+--------------------+-------------+-------------------------------------------+
|[*].\ **cooldown**  |Number       |The cooldown period, in seconds, before    |
|                    |*(Required)* |this particular scaling policy can be      |
|                    |             |executed again. The policy cooldown period |
|                    |             |does not affect the global scaling group   |
|                    |             |cooldown. The minimum value for this       |
|                    |             |parameter is 0 seconds, the maximum value  |
|                    |             |is 86400 seconds (24 hrs).                 |
+--------------------+-------------+-------------------------------------------+
|[*].\ **type**      |Enum         |The type of policy that will be executed   |
|                    |*(Required)* |for the current release, this value can be |
|                    |             |either ``webhook`` or ``schedule``.        |
+--------------------+-------------+-------------------------------------------+
|[*].\ **change**    |Integer      |The change to make in the number of        |
|                    |*(Optional)* |servers in the scaling group. This         |
|                    |             |parameter must be an integer. If the value |
|                    |             |is a positive integer, the number of       |
|                    |             |servers increases. If the value is a       |
|                    |             |negative integer, the number of servers    |
|                    |             |decreases.                                 |
+--------------------+-------------+-------------------------------------------+
|[*].\               |Integer      |The desired server capacity of the scaling |
|**desiredCapacity** |*(Optional)* |the group; that is, how many servers       |
|                    |             |should be in the scaling group. This value |
|                    |             |must be an absolute number, greater than   |
|                    |             |or equal to zero. For example, if this     |
|                    |             |parameter is set to ten, executing the     |
|                    |             |policy brings the number of servers to     |
|                    |             |ten. The minimum allowed value is zero.    |
|                    |             |Note that maxEntities and minEntities for  |
|                    |             |the configured group take precedence over  |
|                    |             |this setting.                              |
+--------------------+-------------+-------------------------------------------+






**Example Create policy: JSON request**


The examples that are provided below show several methods for creating a scaling policy:
* A request to create a policy based on desired capacity
* A request to create a policy based on incremental change
* A request to create a policy based on change percentage
* A request to create a policy based on change percentage scheduled daily, at                                a specific time of day
* A request to create a policy based on change percentage scheduled once, for                                a specific date and time
* A request to create multiple policies,followed by the matching response

The following example shows how to create a webhook-based policy specifying that                            the desired capacity be five servers and setting the cooldown period to 1800                            seconds.

.. code::

   [
      {
         "name":"set group to 5 servers",
         "desiredCapacity":5,
         "cooldown":1800,
         "type":"webhook"
      }
   ]


.. code::

   [
      {
         "name":"scale up by one server",
         "change":1,
         "cooldown":1800,
         "type":"webhook"
      }
   ]


.. code::

   [
      {
         "name":"scale down by 5.5 percent",
         "changePercent":-5.5,
         "cooldown":1800,
         "type":"webhook"
      }
   ]


.. code::

   [
      {
         "name":"scale down by 5.5 percent at 11pm",
         "changePercent":-5.5,
         "cooldown":1800,
         "type":"schedule",
         "args":{
            "cron":"23 * * * *"
         }
      }
   ]


.. code::

   [
     {
       "name": "scale down by 5.5 percent on the 5th",
       "changePercent": -5.5,
       "cooldown": 1800,
       "type": "schedule",
       "args": {
         "at": "2013-12-05T03:12:00Z"
       }
     }
   ]



.. code::


   [
      {
         "change":1,
         "cooldown":1800,
         "name":"scale up by one server",
         "type":"webhook"
      },
      {
         "changePercent":-5.5,
         "cooldown":1800,
         "name":"scale down by 5.5 percent",
         "type":"webhook"
      },
      {
         "cooldown":1800,
         "desiredCapacity":5,
         "name":"set group to 5 servers",
         "type":"webhook"
      },
      {
         "args":{
            "cron":"23 * * * *"
         },
         "changePercent":-5.5,
         "cooldown":1800,
         "name":"scale down by 5.5 percent at 11pm",
         "type":"schedule"
      },
      {
         "args":{
            "at":"2013-12-05T03:12:00Z"
         },
         "changePercent":-5.5,
         "cooldown":1800,
         "name":"scale down by 5.5 percent on the 5th",
         "type":"schedule"
      }
   ]





Response
""""""""""""""""










**Example Create policy: JSON response**


.. code::

   {
      "policies":[
         {
            "args":{
               "at":"2013-12-05T03:12:00Z"
            },
            "changePercent":-5.5,
            "cooldown":1800,
            "id":"9f7c5801-6b25-4f5a-af07-4bb752e23d53",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/9f7c5801-6b25-4f5a-af07-4bb752e23d53/",
                  "rel":"self"
               }
            ],
            "name":"scale down by 5.5 percent on the 5th",
            "type":"schedule"
         },
         {
            "cooldown":1800,
            "desiredCapacity":5,
            "id":"b0555a35-b2cb-4f0e-8743-d59e1621b980",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/b0555a35-b2cb-4f0e-8743-d59e1621b980/",
                  "rel":"self"
               }
            ],
            "name":"set group to 5 servers",
            "type":"webhook"
         },
         {
            "args":{
               "cron":"23 * * * *"
            },
            "changePercent":-5.5,
            "cooldown":1800,
            "id":"30707675-8e7c-4ea5-9358-c21648afcf29",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/30707675-8e7c-4ea5-9358-c21648afcf29/",
                  "rel":"self"
               }
            ],
            "name":"scale down by 5.5 percent at 11pm",
            "type":"schedule"
         },
         {
            "change":1,
            "cooldown":1800,
            "id":"1f3bdd08-7aae-4009-a3b7-49aa47fc0876",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/1f3bdd08-7aae-4009-a3b7-49aa47fc0876/",
                  "rel":"self"
               }
            ],
            "name":"scale up by one server",
            "type":"webhook"
         },
         {
            "changePercent":-5.5,
            "cooldown":1800,
            "id":"5afac18c-41e5-49d6-aba8-dec17c0d8ed7",
            "links":[
               {
                  "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/policies/5afac18c-41e5-49d6-aba8-dec17c0d8ed7/",
                  "rel":"self"
               }
            ],
            "name":"scale down by 5.5 percent",
            "type":"webhook"
         }
      ]
   }
