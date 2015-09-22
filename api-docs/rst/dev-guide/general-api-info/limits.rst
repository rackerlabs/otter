.. _limits:

Limits 
~~~~~~~~~

All accounts, by default, have a preconfigured set of thresholds (or
limits) to manage capacity and prevent abuse of the system. The system
recognizes *rate limits* and *absolute limits* . Rate limits are
thresholds that are reset after a certain amount of time passes.
Absolute limits are fixed.

.. _rate-limits:

Rate limits
^^^^^^^^^^^^

Rate limits are specified in terms of both a human-readable wildcard URI
and a machine-processable regular expression. The regular expression
boundary matcher '^' takes effect after the root URI path.

For example, the regular expression ``^/v1.0/execute`` matches the
bolded portion of the following URI:

https://ord.autoscale.api.rackspacecloud.com **/v1.0/execute**.

For any user, all Auto Scale operations are limited to 1,000 calls per
minute.

In addition, the following table specifies the default rate limits for
specific Auto Scale API operations:

**Table: Default Rate Limits**

+--------+----------------------+--------------------------+-----------------+
| Method | URI                  | RegEx                    | Default         |
+========+======================+==========================+=================+
| GET,   | ``/v1.0/execute/*``  | ``/v1\\.0/execute/(.*)`` | 10 per second   |
| PUT,   |                      |                          |                 |
| POST,  |                      |                          |                 |
| DELETE |                      |                          |                 |
+--------+----------------------+--------------------------+-----------------+
| GET,   | ``/v1.0/tenantId/*`` | ``/v1\\.0/([0-9]+)/.+``  | 1000 per minute |
| PUT,   |                      |                          |                 |
| POST,  |                      |                          |                 |
| DELETE |                      |                          |                 |
+--------+----------------------+--------------------------+-----------------+

Rate limits are applied in order relative to the verb, going from least
to most specific. For example, although the general threshold for
operations to ``/v1/0/*`` is 1,000 per minute, one cannot **POST** to
``/v1.0/execute*``\ more than 1 time per second, which is 60 times per
minute.

If you exceed the thresholds established for your account, a ``413 Rate
Control`` HTTP response is returned with a ``Retry-After`` header to
notify the client when it can attempt to try again.

.. _absolute-limits:

Absolute limits
^^^^^^^^^^^^^^^^

**Table: Absolute Limits**

+----------+---------------------------------------------------+--------+
| Name     | Description                                       | Limits |
+==========+===================================================+========+
| Groups   | Maximum number of groups allowed for your account | 1000   |
+----------+---------------------------------------------------+--------+
| Policies | Maximum volume of Policies per Group              | 100    |
+----------+---------------------------------------------------+--------+
| Webhooks | Maximum volume of Webhooks per Policy             | 25     |
+----------+---------------------------------------------------+--------+

