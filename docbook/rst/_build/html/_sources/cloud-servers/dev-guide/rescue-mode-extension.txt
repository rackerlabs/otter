=====================
Rescue Mode Extension
=====================

Rescue mode creates a new Cloud Server with the file system for the
specified Cloud Server system mounted to fix file system and
configuration errors.

When you place a server in rescue mode, the following events occur:

#. The server is shut down.

#. A new server is created, as follows:

   -  The new server is based on the image from which the original
      server was created, with a random password. This password is
      returned to you in a response to issuing the rescue mode API call.

   -  The new server has a secondary disk that is the file system of the
      original server.  Use the clean rescue server to fix problems on
      the original server.

To place a server in rescue mode, issue the request body in a **POST**
request to **/servers/**\ *``id``*\ **/action**. When you put a server
into rescue mode, you cannot use it until its status goes from
``ACTIVE`` to ``RESCUE``. This does not happen immediately.

After you resolve any problems and reboot the rescued server, you can
unrescue the server, which restores the repaired image to running state
with its original password. The unrescue operation does not return a
response body. The HTTP status code is 202 (Accepted) for a successful
unrescue.

The following JSON request and response examples show how to place a
server in rescue mode:

.. code::

    {
    "rescue" : null
    } 

After you place a server in rescue mode, the following response is
returned:

.. code::

    {
        "adminPass" : "Qy7gCeHeYaT7"
    } 

The following  example shows how to unrescue a server that is in
rescue mode:

.. code::

    {
    "unrescue" : null
    }

