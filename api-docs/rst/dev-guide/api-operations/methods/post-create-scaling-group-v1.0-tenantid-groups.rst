

.. _post-create-scaling-group-v1.0-tenantid-groups:

Create scaling group
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    POST /v1.0/{tenantId}/groups

This operation creates a scaling group.

This operation creates a scaling group or a collection of servers and load balancers that are managed by a scaling policy. To describe the group, specify the scaling group configuration, launch configuration, and optional scaling policies in the request body in JSON format.

If the request succeeds, the response body describes the created group in JSON format. The response includes an ID and links for the group.

The number of resources entities that are specified in ``minEntities`` and ``maxEntities`` overrides the amount of resources that can be specified in a policy. See also :ref:`Using the min and max values with policies <using-min-and-max-values>`.

You can specify custom metadata for your group configuration using the optional ``metadata`` parameter.

.. note::

      Group metadata is stored within the Auto Scale API and can be queried. You can use the ``metadata`` parameter for
      customer automation, but it does not change any functionality in Autoscale.







This table shows the possible response codes for this operation:


+-------------------------+---------------------------+------------------------+
|Response Code            |Name                       |Description             |
+=========================+===========================+========================+
|201                      |Created                    |The scaling group has   |
|                         |                           |been created.Creates an |
|                         |                           |auto scaling endpoint.  |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidJsonError           |The request is refused  |
|                         |                           |because the body was    |
|                         |                           |invalid JSON".          |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The "flavorRef" value   |
|                         |                           |is invalid.             |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The "imageRef" value is |
|                         |                           |invalid or not active.  |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The base64 encoding for |
|                         |                           |the "path" argument in  |
|                         |                           |the "personality"       |
|                         |                           |parameter is invalid.   |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The content of the      |
|                         |                           |files in the            |
|                         |                           |"personality" parameter |
|                         |                           |exceeds the maximum     |
|                         |                           |size limit allowed.     |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The load balancer ID    |
|                         |                           |provided is invalid.    |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidLaunchConfiguration |The number of files in  |
|                         |                           |the "personality"       |
|                         |                           |parameter exceeds       |
|                         |                           |maximum limit.          |
+-------------------------+---------------------------+------------------------+
|400                      |InvalidMinEntities         |The "minEntities" value |
|                         |                           |is greater than the     |
|                         |                           |"maxEntities" value.    |
+-------------------------+---------------------------+------------------------+
|400                      |ValidationError            |The request body had    |
|                         |                           |valid JSON but with     |
|                         |                           |unexpected properties   |
|                         |                           |or values in it. Please |
|                         |                           |note that there can be  |
|                         |                           |many combinations that  |
|                         |                           |cause this error. We    |
|                         |                           |will try to list the    |
|                         |                           |most common mistakes    |
|                         |                           |users are likely to     |
|                         |                           |make in a particular    |
|                         |                           |request. ".             |
+-------------------------+---------------------------+------------------------+
|401                      |InvalidCredentials         |The X-Auth-Token the    |
|                         |                           |user supplied is bad.   |
+-------------------------+---------------------------+------------------------+
|403                      |Forbidden                  |The user does not have  |
|                         |                           |permission to perform   |
|                         |                           |the resource; for       |
|                         |                           |example, the user only  |
|                         |                           |has an observer role    |
|                         |                           |and attempted to        |
|                         |                           |perform something only  |
|                         |                           |available to a user     |
|                         |                           |with an admin role.     |
|                         |                           |Note, some API nodes    |
|                         |                           |also use this status    |
|                         |                           |code for other things.  |
+-------------------------+---------------------------+------------------------+
|405                      |InvalidMethod              |The method used is      |
|                         |                           |unavailable for the     |
|                         |                           |endpoint.               |
+-------------------------+---------------------------+------------------------+
|413                      |RateLimitError             |The user has surpassed  |
|                         |                           |their rate limit.       |
+-------------------------+---------------------------+------------------------+
|415                      |UnsupportedMediaType       |The request is refused  |
|                         |                           |because the content     |
|                         |                           |type of the request is  |
|                         |                           |not "application/json". |
+-------------------------+---------------------------+------------------------+
|422                      |ScalingGroupOverLimitsError|The user has reached    |
|                         |                           |their quota for scaling |
|                         |                           |groups, currently 100.  |
+-------------------------+---------------------------+------------------------+
|500                      |InternalError              |An error internal to    |
|                         |                           |the application has     |
|                         |                           |occurred, please file a |
|                         |                           |bug report.             |
+-------------------------+---------------------------+------------------------+
|503                      |ServiceUnavailable         |The requested service   |
|                         |                           |is unavailable, please  |
|                         |                           |file a bug report.      |
+-------------------------+---------------------------+------------------------+


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





This table shows the body parameters for the request:

+---------------------------------------------------+-------------+---------------------------------------------------+
|Name                                               |Type         |Description                                        |
+===================================================+=============+===================================================+
|\ **launchConfiguration**                          |Object       |A launch configuration defines what to do when a   |
|                                                   |*(Required)* |new server is created, including information about |
|                                                   |             |the server image, the flavor of the server image,  |
|                                                   |             |and the cloud load balancer or RackConnectV3 load  |
|                                                   |             |balancer pool to which to connect. You must set    |
|                                                   |             |the ``type`` parameter to ``launch_server``.       |
|                                                   |             |                                                   |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.\ **args**                     |Object       |The configuration used to create new servers in    |
|                                                   |*(Required)* |the scaling group. You must specify the ``server`` |
|                                                   |             |attribute, and can also specify the optional       |
|                                                   |             |``loadBalancers`` attribute. Most launch           |
|                                                   |             |configurations have both a server and a cloud load |
|                                                   |             |balancer or RackConnectV3 load balancer pool       |
|                                                   |             |configured.                                        |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.\ **loadBalancers**       |Array        |One or more cloud load balancers or RackConnectV3  |
|                                                   |*(Optional)* |load balancer pools to which to add new servers.   |
|                                                   |             |For background information and an example          |
|                                                   |             |configuration, see :ref:`Cloud Bursting with       |
|                                                   |             |RackConnect v3 <cloud-bursting>`. All servers are  |
|                                                   |             |added to these load balancers with the IP          |
|                                                   |             |addresses of their ServiceNet network. All servers |
|                                                   |             |are enabled and equally weighted. Any new servers  |
|                                                   |             |that are not connected to the ServiceNet network   |
|                                                   |             |are not added to any load balancers.               |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.loadBalancers.[*].\       |Integer      |The port number of the service (on the new         |
|**port**                                           |*(Required)* |servers) to use for this particular cloud load     |
|                                                   |             |balancer. In most cases, this port number is 80.   |
|                                                   |             |.. note:: This parameter is NOT required if you    |
|                                                   |             |are using RackConnectV3 and should be left empty.  |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.loadBalancers.[*].\       |String       |The ID of the cloud load balancer, or              |
|**loadBalancerId**                                 |*(Required)* |RackConnectV3 load balancer pool, to which new     |
|                                                   |             |servers are added. For cloud load balancers set    |
|                                                   |             |the ID as an integer, for RackConnectV3 set the    |
|                                                   |             |UUID as a string. NOTE that when using             |
|                                                   |             |RackConnectV3, this value is supplied to you by    |
|                                                   |             |Rackspace Support after they configure your load   |
|                                                   |             |balancer pool.                                     |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.\ **server**              |Object       |The attributes that Auto Scale uses to create a    |
|                                                   |*(Required)* |new server. The attributes that you specify for    |
|                                                   |             |the server entity apply to all new servers in the  |
|                                                   |             |scaling group, including the server name. Note the |
|                                                   |             |server arguments are directly passed to nova when  |
|                                                   |             |creating a server. For more information see        |
|                                                   |             |`Create Your Server with the nova Client           |
|                                                   |             |<http://docs.rackspace.com/servers/api/v2/cs-      |
|                                                   |             |gettingstarted/content/nova_create_server.html>`__ |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.\ **flavorRef**    |String       |The flavor of the server image. Specifies the      |
|                                                   |*(Required)* |flavor ID for the server. A flavor is a resource   |
|                                                   |             |configuration for a server. For more information,  |
|                                                   |             |see :ref:`Server flavors <server-flavors>`.        |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.\ **imageRef**     |String       |The ID of the cloud server image, after which new  |
|                                                   |*(Required)* |server images are created.                         |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.diskConfig         |String       |How the disk on new servers is partitioned. Valid  |
|                                                   |*(Required)* |values are ``AUTO`` " or ``MANUAL``. For non-      |
|                                                   |             |Rackspace server images, this value must always be |
|                                                   |             |``MANUAL``. A non-Rackspace server image would be  |
|                                                   |             |one that you imported using a non-Rackspace        |
|                                                   |             |server. For more information, see the `Disk        |
|                                                   |             |Configuration Extension                            |
|                                                   |             |<http://docs.rackspace.com/servers/api/v2/cs-      |
|                                                   |             |devguide/content/diskconfig_attribute.html>`__     |
|                                                   |             |documentation for Rackspace Cloud Servers.         |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.\ **personality**  |Array        |The file path and/or the content that you want to  |
|                                                   |*(Required)* |inject into a server image. For more information,  |
|                                                   |             |see the `Server personality                        |
|                                                   |             |<http://docs.rackspace.com/servers/api/v2/cs-      |
|                                                   |             |devguide/content/Server_Personality-               |
|                                                   |             |d1e2543.html>`__ documentation for Rackspace Cloud |
|                                                   |             |Servers.                                           |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.personality.[*].\  |String       |The path to the file that contains data that is    |
|**path**                                           |*(Required)* |injected into the file system of the new cloud     |
|                                                   |             |server image.                                      |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.personality.[*].\  |String       |The content items that is injected into the file   |
|**contents**                                       |*(Required)* |system of the new cloud server image.              |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.args.server.\ **user_data**    |String       |The base64 encoded string of your create server    |
|                                                   |*(Optional)* |template.                                          |
+---------------------------------------------------+-------------+---------------------------------------------------+
|launchConfiguration.\ **type**                     |String       |The type of the launch configuration. For this     |
|                                                   |*(Required)* |release, this parameter must be set to             |
|                                                   |             |``launch_server``.                                 |
+---------------------------------------------------+-------------+---------------------------------------------------+
|\ **groupConfiguration**                           |Object       |The configuration options for the scaling group.   |
|                                                   |*(Required)* |The scaling group configuration specifies the      |
|                                                   |             |basic elements of the Auto Scale configuration. It |
|                                                   |             |manages how many servers can participate in the    |
|                                                   |             |scaling group. It specifies information related to |
|                                                   |             |load balancers.                                    |
+---------------------------------------------------+-------------+---------------------------------------------------+
|groupConfiguration.\ **maxEntities**               |Object       |The maximum number of entities that are allowed in |
|                                                   |*(Optional)* |the scaling group. If unconfigured, defaults to    |
|                                                   |             |1000. If this value is provided it must be set to  |
|                                                   |             |an integer between 0 and 1000.                     |
+---------------------------------------------------+-------------+---------------------------------------------------+
|groupConfiguration.\ **name**                      |String       |The name of the scaling group. This name does not  |
|                                                   |*(Required)* |need to be unique.                                 |
+---------------------------------------------------+-------------+---------------------------------------------------+
|groupConfiguration.\ **cooldown**                  |Integer      |The cool-down period before more entities are      |
|                                                   |*(Required)* |added, in seconds. This number must be an integer  |
|                                                   |             |between 0 and 86400 (24 hrs).                      |
+---------------------------------------------------+-------------+---------------------------------------------------+
|groupConfiguration.\ **minEntities**               |Integer      |The minimum number of entities in the scaling      |
|                                                   |*(Required)* |group. This number must be an integer between 0    |
|                                                   |             |and 1000.                                          |
+---------------------------------------------------+-------------+---------------------------------------------------+
|groupConfiguration.\ **metadata**                  |Object       |Optional. Custom metadata for your group           |
|                                                   |*(Optional)* |configuration. You can use the metadata parameter  |
|                                                   |             |for customer automation, but it does not change    |
|                                                   |             |any functionality in Auto Scale. There currently   |
|                                                   |             |is no limitation on depth.                         |
+---------------------------------------------------+-------------+---------------------------------------------------+
|\ **scalingPolicies**                              |Array        |This parameter group specifies configuration       |
|                                                   |*(Required)* |information for your scaling policies. Scaling     |
|                                                   |             |policies specify how to modify the scaling group   |
|                                                   |             |and its behavior. You can specify multiple         |
|                                                   |             |policies to manage a scaling group.                |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*]                                |Array        |An array of scaling policies.                      |
|                                                   |*(Required)* |                                                   |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **name**                     |String       |A name for the scaling policy. This name must be   |
|                                                   |*(Required)* |unique for each scaling policy.                    |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **args**                     |Object       |Additional configuration information for policies  |
|                                                   |*(Optional)* |of type "schedule." This parameter is not required |
|                                                   |             |for policies of type "webhook." This parameter     |
|                                                   |             |must be set to either ``at`` or ``cron``. Both are |
|                                                   |             |mutually exclusive.                                |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].args.\ **cron**                |String       |The recurring time when the policy runs as a cron  |
|                                                   |*(Optional)* |entry. For example, if you set this parameter to   |
|                                                   |             |``1 0 * * *``, the policy runs at one minute past  |
|                                                   |             |midnight (00:01) every day of the month, and every |
|                                                   |             |day of the week. For more information about cron,  |
|                                                   |             |see ` http://en.wikipedia.org/wiki/Cron            |
|                                                   |             |<http://en.wikipedia.org/wiki/Cron>`__.            |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].args.\ **at**                  |String       |The time when this policy runs. This property is   |
|                                                   |*(Optional)* |mutually exclusive with the ``cron`` parameter.    |
|                                                   |             |You must specify seconds when using ``at``. For    |
|                                                   |             |example, if you set ``at: "2013-12-                |
|                                                   |             |05T03:12:00Z"``. If seconds are not specified, a   |
|                                                   |             |400 error is returned. Note, the policy is         |
|                                                   |             |triggered within a 10-second range of the time     |
|                                                   |             |specified.                                         |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **changePercent**            |Number       |The percent change to make in the number of        |
|                                                   |*(Optional)* |servers in the scaling group. If this number is    |
|                                                   |             |positive, the number of servers increases by the   |
|                                                   |             |given percentage. If this parameter is set to a    |
|                                                   |             |negative number, the number of servers decreases   |
|                                                   |             |by the given percentage. The absolute change in    |
|                                                   |             |the number of servers is rounded to the nearest    |
|                                                   |             |integer. This means that if -X% of the current     |
|                                                   |             |number of servers translates to -0.5 or -0.25 or - |
|                                                   |             |0.75 servers, the actual number of servers that    |
|                                                   |             |are shut down is 1. If X% of the current number of |
|                                                   |             |servers translates to 1.2 or 1.5 or 1.7 servers,   |
|                                                   |             |the actual number of servers that are launched is  |
|                                                   |             |2.                                                 |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **cooldown**                 |Number       |The cool-down period, in seconds, before this      |
|                                                   |*(Required)* |particular scaling policy can run again. The cool- |
|                                                   |             |down period does not affect the global scaling     |
|                                                   |             |group cool-down. The minimum value for this        |
|                                                   |             |parameter is 0 seconds, the maximum value is 86400 |
|                                                   |             |seconds (24 hrs).                                  |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **type**                     |Enum         |The type of policy that runs for the current       |
|                                                   |*(Required)* |release, this value can be either ``webhook`` for  |
|                                                   |             |webhook-based policies or ``schedule`` for         |
|                                                   |             |schedule-based policies.                           |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **change**                   |Integer      |The change to make in the number of servers in the |
|                                                   |*(Optional)* |scaling group. This parameter must be an integer.  |
|                                                   |             |If the value is a positive integer, the number of  |
|                                                   |             |servers increases. If the value is a negative      |
|                                                   |             |integer, the number of servers decreases.          |
+---------------------------------------------------+-------------+---------------------------------------------------+
|scalingPolicies.[*].\ **desiredCapacity**          |Integer      |The desired server capacity of the scaling the     |
|                                                   |*(Optional)* |group; that is, how many servers should be in the  |
|                                                   |             |scaling group. This value must be an absolute      |
|                                                   |             |number, greater than or equal to zero. For         |
|                                                   |             |example, if this parameter is set to ten,          |
|                                                   |             |executing the policy brings the number of servers  |
|                                                   |             |to ten. The minimum allowed value is zero. Note    |
|                                                   |             |that the configured group maxEntities and          |
|                                                   |             |minEntities takes precedence over this setting.    |
+---------------------------------------------------+-------------+---------------------------------------------------+





**Example Create scaling group: JSON request**


.. code::

   {
      "launchConfiguration":{
         "args":{
            "loadBalancers":[
               {
                  "port":80,
                  "loadBalancerId":237935
               }
            ],
            "server":{
               "name":"autoscale_server",
               "imageRef":"7cf5ffc3-7b20-46fd-98e4-fefa9908d7e8",
               "flavorRef":"performance1-2",
               "OS-DCF:diskConfig":"AUTO",
               "networks":[
                  {
                     "uuid":"11111111-1111-1111-1111-111111111111"
                  },
                  {
                     "uuid":"00000000-0000-0000-0000-000000000000"
                  }
               ]
            }
         },
         "type":"launch_server"
      },
      "groupConfiguration":{
         "maxEntities":10,
         "cooldown":360,
         "name":"testscalinggroup",
         "minEntities":0
      },
      "scalingPolicies":[
         {
            "cooldown":0,
            "name":"scale up by 1",
            "change":1,
            "type":"schedule",
            "args":{
               "cron":"23 * * * *"
            }
         }
      ]
   }





Response
""""""""""""""""


This table shows the header parameters for the response:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|location                  |Anyuri *(Required)*      |Creates an auto scaling  |
|                          |                         |endpoint.                |
+--------------------------+-------------------------+-------------------------+










**Example Create scaling group: JSON response**


.. code::

   {
      "group":{
         "groupConfiguration":{
            "cooldown":360,
            "maxEntities":10,
            "metadata":{

            },
            "minEntities":0,
            "name":"testscalinggroup"
         },
         "id":"48692442-2dbe-4311-955e-bc29f02ae311",
         "launchConfiguration":{
            "args":{
               "loadBalancers":[
                  {
                     "loadBalancerId":237935,
                     "port":80
                  }
               ],
               "server":{
                  "OS-DCF:diskConfig":"AUTO",
                  "flavorRef":"performance1-2",
                  "imageRef":"7cf5ffc3-7b20-46fd-98e4-fefa9908d7e8",
                  "name":"autoscale_server",
                  "networks":[
                     {
                        "uuid":"11111111-1111-1111-1111-111111111111"
                     },
                     {
                        "uuid":"00000000-0000-0000-0000-000000000000"
                     }
                  ]
               }
            },
            "type":"launch_server"
         },
         "links":[
            {
               "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/",
               "rel":"self"
            }
         ],
         "scalingPolicies":[
            {
               "args":{
                  "cron":"23 * * * *"
               },
               "change":1,
               "cooldown":0,
               "id":"9fa63149-c93d-4116-8069-74d68f48fadc",
               "links":[
                  {
                     "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/policies/9fa63149-c93d-4116-8069-74d68f48fadc/",
                     "rel":"self"
                  }
               ],
               "name":"scale up by 1",
               "type":"schedule"
            }
         ],
         "scalingPolicies_links":[
            {
               "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/policies/",
               "rel":"policies"
            }
         ],
         "state":{
            "active":[

            ],
            "activeCapacity":0,
            "desiredCapacity":0,
            "name":"testscalinggroup",
            "paused":false,
            "pendingCapacity":0
         }
      }
   }
