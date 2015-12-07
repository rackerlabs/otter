.. _using-rackspace-autoscale:

Create and manage scaling groups
--------------------------------

You can use the examples in the following sections to create scaling groups
using a schedule-based configuration by using the Rackspace Auto Scale API.
Before running the examples, review the :ref:`Rackspace Auto Scale concepts
<concepts>` to understand the API workflow, scaling group configurations,
and use cases.

.. note::
     These examples use the ``$API_ENDPOINT``, ``$AUTH_TOKEN``, and ``$TENANT_ID`` environment
     variables to specify the API endpoint, authentication token, and project ID values
     for accessing the service. Make sure you
     :ref:`configure these variables<configure-environment-variables>` before running the
     code samples.

.. include:: examples/list-server-images.rst
.. include:: examples/create-server.rst
.. include:: examples/create-server-image.rst
.. include:: examples/create-scaling-group.rst
.. include:: examples/delete-scaling-group.rst
