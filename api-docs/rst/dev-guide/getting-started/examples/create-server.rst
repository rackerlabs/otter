.. _create-server:

Create a cloud server
~~~~~~~~~~~~~~~~~~~~~
After you have obtained the imageID for the server image you want
to create, you need to create your cloud server. Auto Scale will
use the configuration info in this server image as a blueprint
for create new server images.

You can create a server using one of the following methods:

  1. Create a server through the :mycloud:`Cloud Control Panel <>`.

  2. Create a server through the Cloud Servers API by using a
     :rax-devdocs:`Create Server
     <cloud-servers/v2/developer-guide/#post-create-server-servers>` request.
