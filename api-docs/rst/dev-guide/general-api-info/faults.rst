.. _faults:

Faults
~~~~~~~~~

If any Rackspace Auto Scale request results in an error, the service
returns an appropriate 4 xx or 5 xx HTTP status code, and the following
information in the body:

-  Title

-  Exception type

-  HTTP status code

-  Message

For Auto Scale users, common faults are caused by invalid
configurations. For example, trying to boot a server from an image that
does not exist causes a fault, as does trying to attach a load balancer
to a scaling group that does not exist.

An example of error message syntax:

 
**Example: Error message syntax**

.. code::  

    { "error": {
     "type": "failure type",
     "code": HTTP status code,
     "message": "detailed message",
     "details": "any specific details about the error"
     }
    }
                            

An example of an error message:

 
**Example: Error message: NoSuchScalingGroup**

.. code::  

    { "error": {
     "type": "NoSuchScalingGroupError",
     "code": 404,
     "message": "No such scaling group 5154258e-d7b7-43a3-a8a9-708b66fae2a2 for tenant 823364",
     "details": ""
     }
    }
                            

Error information for each API operation is included with the
description of that operation in the API reference section.
