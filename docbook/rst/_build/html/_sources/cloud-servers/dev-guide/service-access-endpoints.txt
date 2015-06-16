========================
Service Access Endpoints
========================

The Rackspace Cloud Servers service is a regionalized service. The user
of the service is therefore responsible for selecting the appropriate
regional endpoint to ensure access to servers, networks, or other Cloud
services.

.. tip::
   To help you decide which regionalized endpoint to use, read about
   special considerations for choosing a data center at
   http://www.rackspace.com/knowledge_center/article/about-regions.

If you are working with cloud servers that are in one of the Rackspace
data centers, using the ServiceNet endpoint in the same data center has
no network costs and provides a faster connection. ServiceNet is the
data center internet network. In your authentication response service
catalog, it is listed as InternalURL. If you are working with servers
that are not in one of the Rackspace data centers, you must use a public
endpoint to connect. In your authentication response, public endpoints
are listed as publicURL. If you are working with servers in multiple
data centers or have a mixed environment where you have servers in your
data centers and in Rackspace data centers, use a public endpoint
because it is accessible from all the servers in the different
environments.

.. note::
   You should copy the base URLs directly from the catalog rather than
   trying to construct them manually.

Rackspace Cloud Identity returns a service catalog, which includes
regional endpoints with your account ID. Your account ID, also known as
project ID or tenant ID, refers to your Rackspace account number.

.. tip:: 
   If you do not know your account ID or which data center you are
   working in, you can find that information in your Cloud Control Panel at
   `mycloud.rackspace.com. <http://mycloud.rackspace.com>`__

