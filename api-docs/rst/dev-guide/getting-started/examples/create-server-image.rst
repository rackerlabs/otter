.. _create-server-image:

Create a cloud server image
~~~~~~~~~~~~~~~~~~~~~~~~~~~
After you have created a Cloud Server, you need to create an image,
which Auto Scale will use to create new servers.

You can create a server image using one of the following methods:

  1. Create a server image through the :mycloud:`Cloud Control Panel <>`.
     Make sure to record the imageID value for the image you have created.

  2. Create a server image through the Cloud Servers API by using a
     :rax-devdocs:`Create Image request
     <cloud-servers/v2/developer-guide/#post-create-image-of-specified-server-servers-server-id-actions>`
     to obtain the imageID value, use a
     :rax-devdocs:`List Images request <cloud-servers/v2/developer-guide/#get-retrieve-list-of-images-images>`.
