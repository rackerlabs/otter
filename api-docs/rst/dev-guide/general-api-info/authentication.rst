.. _authentication-ovw:

==============
Authentication
==============

Each REST request against the Cloud Big Data service requires the inclusion of a specific
authorization token, supplied in the ``X-Auth-Token`` HTTP header of each API request.
You get a token by submitting an authentication request with valid account credentials to
the following Rackspace Cloud Identity API service endpoint:

.. code::

       https://identity.api.rackspacecloud.com/v2.0

For details see the following information:

- :ref:`Authenticate to the Rackspace Cloud<authenticate-to-cloud>`
- :rax-devdocs:`Rackspace Cloud Identity API developer documentation
  <cloud-identity/v2/developer-guide/>`
