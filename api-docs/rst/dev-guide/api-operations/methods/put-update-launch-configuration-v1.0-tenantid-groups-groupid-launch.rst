

.. _put-update-launch-configuration-v1.0-tenantid-groups-groupid-launch:

Update launch configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    PUT /v1.0/{tenantId}/groups/{groupId}/launch

This operation updates an existing launch configuration for the specified scaling group.

To change the launch configuration, specify the new configuration in the request body in JSON format. Configuration elements include from which image to create a server, which load balancers to join the server to, which networks to add the server to, and other metadata. If the update is successful, no response body is returned.

.. note::
   All Rackspace Auto Scale update (**PUT**) operations completely replace the configuration being updated. Empty values (for example, { } )in the update are accepted and overwrite previously specified parameters. New parameters can be specified. All create (**POST**) parameters, even optional ones, are required for the update operation. 





This table shows the possible response codes for this operation:


+-------------------------+---------------------------+------------------------+
|Response Code            |Name                       |Description             |
+=========================+===========================+========================+
|204                      |Success But No Content     |The update launch       |
|                         |                           |configuration request   |
|                         |                           |succeeded.              |
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
|400                      |ValidationError            |The request body had    |
|                         |                           |valid JSON but with     |
|                         |                           |unexpected properties   |
|                         |                           |or values in it. Please |
|                         |                           |note that there can be  |
|                         |                           |many combinations that  |
|                         |                           |cause this error.       |
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
|404                      |NoSuchScalingGroupError    |The specified scaling   |
|                         |                           |group was not found.    |
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
|{groupId}                 |Uuid *(Required)*        |A scaling group.         |
+--------------------------+-------------------------+-------------------------+





This table shows the body parameters for the request:

+-------------------------------+-------------+---------------------------------------------------+
|Name                           |Type         |Description                                        |
+===============================+=============+===================================================+
|\ **args**                     |Object       |The configuration used to create new servers in    |
|                               |*(Optional)* |the scaling group. You must specify ``server``     |
|                               |             |attribute, and can also specify the optional       |
|                               |             |``loadBalancers`` attribute. Most launch           |
|                               |             |configurations have both a server and a cloud load |
|                               |             |balancer or RackConnectV3 load balancer pool       |
|                               |             |configured.                                        |
+-------------------------------+-------------+---------------------------------------------------+
|args.\ **loadBalancers**       |Array        |One or more load balancers to which to add         |
|                               |*(Optional)* |servers. All servers are added to these load       |
|                               |             |balancers with the IP addresses of their           |
|                               |             |ServiceNet network. All servers are enabled and    |
|                               |             |equally weighted. Any new servers that are not     |
|                               |             |connected to the ServiceNet network are not added  |
|                               |             |to any load balancers.                             |
+-------------------------------+-------------+---------------------------------------------------+
|args.loadBalancers.[\*].\      |Integer      |The port number of the service (on the new         |
|**port**                       |*(Required)* |servers) to use for this particular load balancer. |
|                               |             |In most cases, this port number is 80. NOTE that   |
|                               |             |when using RackConnectV3, instead of a cloud load  |
|                               |             |balancer, leave this parameter empty.              |
+-------------------------------+-------------+---------------------------------------------------+
|args.loadBalancers.[\*].\      |String       |The ID of the cloud load balancer, or              |
|**loadBalancerId**             |*(Required)* |RackConnectV3 load balancer pool, to which new     |
|                               |             |servers are added. For cloud load balancers set    |
|                               |             |the ID as an integer, for RackConnectV3 set the    |
|                               |             |UUID as a string. Note that when using             |
|                               |             |RackConnectV3, this value is supplied to you by    |
|                               |             |Rackspace Support after they configure your load   |
|                               |             |balancer pool.                                     |
+-------------------------------+-------------+---------------------------------------------------+
|args.\ **draining_timeout**    |Integer      |Specifies the number of seconds for which the      |
|                               |*(Optional)* |cloud load balancer node associated with the server|
|                               |             |that is being deleted will be put in DRAINING mode |
|                               |             |before the node is actually being deleted followed |
|                               |             |by the server. Must be between 30 and 3600         |
|                               |             |inclusive.                                         |
+-------------------------------+-------------+---------------------------------------------------+
|args.\ **server**              |Object       |The attributes that Auto Scale uses to create a    |
|                               |*(Required)* |new server. For more information, see `Create      |
|                               |             |Servers                                            |
|                               |             |<http://docs.rackspace.com/servers/api/v2/cs-      |
|                               |             |devguide/content/CreateServers.html>`. The         |
|                               |             |attributes that are specified for the server       |
|                               |             |entity will apply to all new servers in the        |
|                               |             |scaling group, including the server name.          |
+-------------------------------+-------------+---------------------------------------------------+
|args.server.\ **flavorRef**    |String       |The flavor of the server image. Specifies the      |
|                               |*(Required)* |flavor Id for the server. A flavor is a resource   |
|                               |             |configuration for a server. For more information   |
|                               |             |on available flavors, see the `Server flavors      |
|                               |             |<http://docs.rackspace.com/cas/api/v1.0/autoscale- |
|                               |             |devguide/content/server-flavors.html>` section.    |
+-------------------------------+-------------+---------------------------------------------------+
|args.server.\ **imageRef**     |String       |The ID of the cloud server image from which new    |
|                               |*(Required)* |server images will be created.                     |
+-------------------------------+-------------+---------------------------------------------------+
|args.server.personality.[\*].\ |String       |The path to the file that contains data that is    |
|**path**                       |*(Required)* |be injected into the file system of the new cloud  |
|                               |             |server image.                                      |
+-------------------------------+-------------+---------------------------------------------------+
|args.server.personality.[\*].\ |String       |The content items that will be injected into the   |
|**contents**                   |*(Required)* |file system of the new cloud server image.         |
+-------------------------------+-------------+---------------------------------------------------+





**Example Update launch configuration: JSON request**


.. code::

   {
      "type":"launch_server",
      "args":{
         "server":{
            "flavorRef":"performance1-4",
            "name":"webhead",
            "imageRef":"0d589460-f177-4b0f-81c1-8ab8903ac7d8",
            "OS-DCF:diskConfig":"AUTO",
            "metadata":{
               "mykey":"myvalue"
            },
            "personality":[

            ],
            "networks":[
               {
                  "uuid":"11111111-1111-1111-1111-111111111111"
               }
            ]
         },
         "loadBalancers":[
            {
               "loadBalancerId":2200,
               "port":8081
            }
         ],
        "draining_timeout": 30
      }
   }





Response
""""""""""""""""






This operation does not return a response body.
