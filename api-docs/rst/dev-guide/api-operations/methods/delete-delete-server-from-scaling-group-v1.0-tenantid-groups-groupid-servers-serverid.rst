
.. _delete-delete-server-from-scaling-group-v1.0-tenantid-groups-groupid-servers-serverid:

Delete server from scaling group
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    DELETE /v1.0/{tenantId}/groups/{groupId}/servers/{serverId}

This operation deletes and replaces a specified server in a scaling group.

You can delete and replace a server in a scaling group with a new server in that scaling group. By default, the specified server is deleted and replaced. The replacement server has the current launch configuration settings and a different IP address. 

.. note::

The ``replace`` parameter is optional for this method. The default setting is ``replace=true``, even if this parameter is not passed. Use ``replace=false`` if you do not want the deleted server replaced. 

Similarly, the ``purge`` parameter is also optional. Default is ``purge=true``, which automatically deletes the server from the account. Use ``purge=false`` if you do not want the deleted server removed from the account. You may want to do this if you want to investigate the server. 

..note::

This operation can be useful if you have deleted a server by using a nova command or another method that Auto Scale does not recognize. In those cases, even though the server is deleted, Auto Scale calculates that the server still exists. You can use this operation to rectify this error and bring Auto Scale in sync with the previously unrecognized delete server operation.

.. note::

Deleting and replacing the server takes some time, how long depends mainly on the server image and complexity of the launch configuration settings of the replacement server. 







This table shows the possible response codes for this operation:


+----------------------+--------------------------------+----------------------+
|Response Code         |Name                            |Description           |
+======================+================================+======================+
|202                   |Accepted                        |The request           |
|                      |                                |succeeded. No         |
|                      |                                |response body is      |
|                      |                                |returned.             |
+----------------------+--------------------------------+----------------------+
|401                   |InvalidCredentials              |The X-Auth-Token the  |
|                      |                                |user supplied is bad. |
+----------------------+--------------------------------+----------------------+
|403                   |CannotDeleteServerBelowMinError |The server cannot be  |
|                      |                                |deleted and not       |
|                      |                                |replaced because      |
|                      |                                |doing so would        |
|                      |                                |violate the           |
|                      |                                |configured            |
|                      |                                |"minEntities." Note   |
|                      |                                |that this error could |
|                      |                                |only occur if the     |
|                      |                                |"replace=false"       |
|                      |                                |argument is used.     |
+----------------------+--------------------------------+----------------------+
|403                   |Forbidden                       |The user does not     |
|                      |                                |have permission to    |
|                      |                                |perform the resource; |
|                      |                                |for example, the user |
|                      |                                |only has an observer  |
|                      |                                |role and attempted to |
|                      |                                |perform something     |
|                      |                                |only available to a   |
|                      |                                |user with an admin    |
|                      |                                |role. Note, some API  |
|                      |                                |nodes also use this   |
|                      |                                |status code for other |
|                      |                                |things.               |
+----------------------+--------------------------------+----------------------+
|404                   |NoSuchScalingGroupError         |The specified scaling |
|                      |                                |group was not found.  |
+----------------------+--------------------------------+----------------------+
|404                   |ServerNotFoundError             |The specified server  |
|                      |                                |was not found.        |
+----------------------+--------------------------------+----------------------+
|405                   |InvalidMethod                   |The method used is    |
|                      |                                |unavailable for the   |
|                      |                                |endpoint.             |
+----------------------+--------------------------------+----------------------+
|413                   |RateLimitError                  |The user has          |
|                      |                                |surpassed their rate  |
|                      |                                |limit.                |
+----------------------+--------------------------------+----------------------+
|500                   |InternalError                   |An error internal to  |
|                      |                                |the application has   |
|                      |                                |occurred, please file |
|                      |                                |a bug report.         |
+----------------------+--------------------------------+----------------------+
|503                   |ServiceUnavailable              |The requested service |
|                      |                                |is unavailable,       |
|                      |                                |please file a bug     |
|                      |                                |report.               |
+----------------------+--------------------------------+----------------------+


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
|{serverId}                |Uuid *(Required)*        |The Nova server ID for   |
|                          |                         |the server you want to   |
|                          |                         |delete from the scaling  |
|                          |                         |group.                   |
+--------------------------+-------------------------+-------------------------+



This table shows the query parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|replace                   |Boolean *(Optional)*     |Defaults to              |
|                          |                         |``replace=true`` if not  |
|                          |                         |passed. Set              |
|                          |                         |``replace=false`` to     |
|                          |                         |delete the server        |
|                          |                         |without replacing it.    |
+--------------------------+-------------------------+-------------------------+
|purge                     |Boolean *(Optional)*     |Defaults to              |
|                          |                         |``purge=true`` if not    |
|                          |                         |passed. Set              |
|                          |                         |``purge=false`` to       |
|                          |                         |delete the server from   |
|                          |                         |the group without        |
|                          |                         |removing it from the     |
|                          |                         |account.                 |
+--------------------------+-------------------------+-------------------------+



This table shows the body parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|serverId                  |String *(Required)*      |Set the ID of the server |
|                          |                         |you want to delete.      |
+--------------------------+-------------------------+-------------------------+




Response
""""""""""""""""




This operation does not return a response body.




