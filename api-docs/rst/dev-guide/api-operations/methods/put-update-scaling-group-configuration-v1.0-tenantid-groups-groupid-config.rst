

.. _put-update-scaling-group-configuration-v1.0-tenantid-groups-groupid-config:

Update scaling group configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    PUT /v1.0/{tenantId}/groups/{groupId}/config

This operation updates the configuration for the scaling group.

This operation updates the configuration of an existing scaling group. To change the configuration, specify the new configuration in the request body in JSON format. Configuration elements include the minimum number of entities, the maximum number of entities, the global cooldown time, and other metadata. If the update is successful, no response body is returned.

.. note::
   All Rackspace Auto Scale update (**PUT**) operations completely replace the configuration being updated. Empty values (for example, { } )in the update are accepted and overwrite previously specified parameters. New parameters can be specified. All create (**POST**) parameters, even optional ones, are required for the update operation. 
   
   



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|204                       |Success But No Content   |The update group         |
|                          |                         |configuration request    |
|                          |                         |succeeded.               |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidJsonError         |The request is refused   |
|                          |                         |because the body was     |
|                          |                         |invalid JSON".           |
+--------------------------+-------------------------+-------------------------+
|400                       |InvalidMinEntities       |The minEntities value is |
|                          |                         |greater than the         |
|                          |                         |maxEntities value.       |
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





This table shows the body parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|\ **maxEntities**         |Object *(Required)*      |The maximum number of    |
|                          |                         |entities that are        |
|                          |                         |allowed in the scaling   |
|                          |                         |group. If left           |
|                          |                         |unconfigured, defaults   |
|                          |                         |to 1000. If this value   |
|                          |                         |is provided it must be   |
|                          |                         |set to an integer        |
|                          |                         |between 0 and 1000.      |
+--------------------------+-------------------------+-------------------------+
|\ **cooldown**            |Integer *(Required)*     |The cooldown period, in  |
|                          |                         |seconds, before any      |
|                          |                         |additional changes can   |
|                          |                         |happen. This number must |
|                          |                         |be an integer between 0  |
|                          |                         |and 86400 (24 hrs).      |
+--------------------------+-------------------------+-------------------------+
|\ **name**                |String *(Required)*      |The name of the scaling  |
|                          |                         |group. This name does    |
|                          |                         |not have to be unique.   |
+--------------------------+-------------------------+-------------------------+
|\ **minEntities**         |Integer *(Required)*     |The minimum number of    |
|                          |                         |entities in the scaling  |
|                          |                         |group. This number must  |
|                          |                         |be an integer between 0  |
|                          |                         |and 1000.                |
+--------------------------+-------------------------+-------------------------+
|\ **metadata**            |Object *(Required)*      |Specifies custom metadata|
|                          |                         |for your group           |
|                          |                         |configuration. You can   |
|                          |                         |use this object to enable|
|                          |                         |custom automation. The   |
|                          |                         |specification does not   |
|                          |                         |affect Auto Scale        |
|                          |                         |functionality. There is  |
|                          |                         |no limitation on depth.  |
+--------------------------+-------------------------+-------------------------+





**Example Update scaling group configuration: JSON request**


.. code::

   {
      "name":"workers",
      "cooldown":60,
      "minEntities":5,
      "maxEntities":100,
      "metadata":{
         "firstkey":"this is a string",
         "secondkey":"1"
      }
   }





Response
""""""""""""""""






This operation does not return a response body.




