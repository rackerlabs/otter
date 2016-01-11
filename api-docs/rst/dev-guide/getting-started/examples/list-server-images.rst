.. _list-server-images:

List cloud server images
~~~~~~~~~~~~~~~~~~~~~~~~
Before you create a server through the Cloud Server API, you need to obtain
a list of available images so that you can choose one for your new server.

After you choose an image, copy its image ID. You use this image ID
when you create the server.

Use the Cloud Servers API to issue a :rax-devdocs:`List Images request
<cloud-servers/v2/developer-guide/#get-retrieve-list-of-images-images>`
to retrieve a list of options available for configuring your server.
The following example shows how to request a list cloud server images.

**Requesting a list of cloud server images**

.. code:: bash

     curl -X GET \
     -H "Content-Type: application/json" \
     -H "X-Auth-token:{auth-token}" \
     https://ord.servers.api.rackspacecloud.com/v2/{tenant-id}/images?type=SNAPSHOT | python -mjson.tool

  1. After creating your server you customize it so that it can process
     your requests. For example, if you are building a webhead
     scaling group, configure Apache to start on launch and serve
     the files that you need.

  2. After you have created and customized your server, save its image
     and record the imageID value that is returned in the response body.
