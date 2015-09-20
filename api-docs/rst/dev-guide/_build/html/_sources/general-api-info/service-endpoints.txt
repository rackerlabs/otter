.. _service-access-endpoints:

Service access endpoints
~~~~~~~~~~~~~~~~~~~~~~~~~~

Rackspace Auto Scale is a regionalized service. The user of the service
is therefore responsible for appropriate replication, caching, and
overall maintenance of Rackspace Auto Scale data across regional
boundaries to other Auto Scale servers.

The following table lists the service access endpoints for Auto Scale
though we recommend checking the endpoints returned in the
authentication response for the most up-to-date information.

..  tip:: 
    To help you decide which regionalized endpoint to use, read the  
    `About Regions <http://ord.admin.kc.rakr.net/knowledge_center/article/about-regions>`__
    article in the Rackspace Knowledge Center.

**Table: Regionalized Service Endpoints**

+------------------------+------------------------------------------------------------------+
| Region                 | Endpoint                                                         |
+========================+==================================================================+
| Dallas/Ft. Worth (DFW) | ``https://dfw.autoscale.api.rackspacecloud.com/v1.0/`` ``1234``/ |
+------------------------+------------------------------------------------------------------+
| Dulles (IAD)           | ``https://iad.autoscale.api.rackspacecloud.com/v1.0/`` ``1234``/ |
+------------------------+------------------------------------------------------------------+
| Hong Kong (HKG)        | ``https://hkg.autoscale.api.rackspacecloud.com/v1.0/`` ``1234``/ |
+------------------------+------------------------------------------------------------------+
| London (LON)           | ``https://lon.autoscale.api.rackspacecloud.com/v1.0/`` ``1234``/ |
+------------------------+------------------------------------------------------------------+
| Sydney (SYD)           | ``https://syd.autoscale.api.rackspacecloud.com/v1.0/`` ``1234``/ |
+------------------------+------------------------------------------------------------------+

Replace the Tenant ID, ``1234``, with your actual Tenant ID.

The value for your tenant ID is listed after the final '/' in the ``publicURL``
field returned by the authentication response. For example, in
`Example 10, “Authentication response for US endpoint:
JSON” <authentication.html#auth-response-example-json>`__\  the
``publicURL`` for Auto Scale is::

   https://ord.autoscale.api.rackspacecloud.com/v1.0/1100111

The ``tenant ID`` is ``1100111``.

