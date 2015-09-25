

.. _post-execute-anonymous-webhook-v1.0-execute-capability-version-capability-hash:

Execute anonymous webhook
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code::

    POST /v1.0/execute/{capability_version}/{capability_hash}


This operation runs an anonymous webhook.



This table shows the possible response codes for this operation:


+--------------------------+-------------------------+-------------------------+
|Response Code             |Name                     |Description              |
+==========================+=========================+=========================+
|202                       |Accepted                 |The execute webhook      |
|                          |                         |request was accepted.    |
+--------------------------+-------------------------+-------------------------+


Request
""""""""""""""""




This table shows the URI parameters for the request:

+--------------------------+-------------------------+-------------------------+
|Name                      |Type                     |Description              |
+==========================+=========================+=========================+
|{capability_hash}         |String *(Required)*      |                         |
+--------------------------+-------------------------+-------------------------+
|{capability_version}      |String *(Required)*      |                         |
+--------------------------+-------------------------+-------------------------+





This operation does not accept a request body.




Response
""""""""""""""""






This operation does not return a response body.




