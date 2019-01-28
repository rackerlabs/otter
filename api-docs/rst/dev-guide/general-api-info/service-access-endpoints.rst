.. _service-access-endpoints:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Service access and endpoints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The Cloud Auto Scale service is a regionalized service that allows
customers to select the
regional endpoint where the Cloud Auto Scale service is provisioned.

.. tip::
     To help you decide which regionalized endpoint to use, see the
     considerations for choosing a data center in the
     :how-to:`About regions <about-regions>` Rackspace Knowledge
     Center article.

**Regionalized service endpoints**

+------------------------+---------------------------------------------------------+
| Region                 | Endpoint                                                |
+========================+=========================================================+
| Chicago (ORD)          | https://ord.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+
| Dallas/Ft. Worth (DFW) | https://dfw.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+
| Hong Kong (HKG)        | https://hkg.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+
| London (LON)           | https://lon.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+
| Northern Virginia (IAD)| https://iad.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+
| Sydney (SYD)           | https://syd.autoscale.api.rackspacecloud.com/v1.0/      |
+------------------------+---------------------------------------------------------+

.. note::
   You should copy the base URLs directly from the catalog rather than
   trying to construct them manually.

   The Identity service returns an endpoint with your account ID.
   Note the following information about account ID:

   * Account ID from the Identity service is the same as the Project ID given
     by the ``X-Project-ID`` header set. (You might also see account ID
     or project ID referred to as tenant ID.)
   * You do not have to provide the account ID for the Cloud Auto Scale
     API if you have the ``X-Project-ID`` header set. (In this case, the Cloud
     Auto Scale API works with or without the account ID specified.)
   * Without the ``X-Project-ID`` header, you receive an auth error if
     the account ID is not in the URL.
   * If the account ID is in the URL, the Cloud Auto Scale API will use
     that ID in place of the ``X-Project-ID`` header.
   * Account ID and Project ID refer to your Rackspace account number.

.. tip::
   If you do not know your account ID or which data center you are
   working in, you can find that information in the
   :mycloud:`Cloud Control Panel <>`.
