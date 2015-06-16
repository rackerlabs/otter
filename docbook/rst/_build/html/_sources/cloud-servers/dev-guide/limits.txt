======
Limits
======

Accounts are configured with thresholds, or limits, that manage capacity
and prevent abuse of the system.

The system recognizes the following types of limits:

-  *rate limits*. Control the frequency at which the user can issue
   specific API requests. See :ref:`rate-limits`.

-  *absolute limits*. Control the total number of specific objects that
   the user can possess simultaneously. See :ref:`absolute-limits`.

To query the limits programmatically, see :ref:`get-limits`.

.. _rate-limits:

Rate Limits
~~~~~~~~~~~

Rate limits control the frequency at which the user can issue specific
API requests.

Rate limits are reset after a certain amount of time passes. To request
a rate limit increase, contact Rackspace.

Rate limits are specified in terms of both a human-readable wild-card
URI and a machine-processable regular expression. The human-readable
limit is intended for displaying in graphical user interfaces. The
machine-processable form is intended to be used directly by client
applications.

The regular expression boundary matcher ``^`` for the rate limit takes
effect after the root URI path. For example, the regular expression
``^/servers`` would match the resources portion of the following URI::

    https://dfw.servers.api.rackspacecloud.com/v2/010101/***servers***

The following table lists the default rate limits:

**Table: Default Rate Limits**

+------------+------------------------------+----------------------+----------+
| Verb       | URI                          | Value                | Unit     |
+------------+------------------------------+----------------------+----------+
| **GET**    | \*                           | 1000                 | minute   |
+------------+------------------------------+----------------------+----------+
| **GET**    | \servers\{id}\               | 25                   | minute   |
|            |  os-virtual-interfacesv2     |                      |          |
+------------+------------------------------+----------------------+----------+
| **POST**   | \*                           | 100                  | minute   |
+------------+------------------------------+----------------------+----------+
| **POST**   | \os-networksv2               | 100                  | day      |
+------------+------------------------------+----------------------+----------+
| **POST**   | \servers                     | 1000                 | day      |
+------------+------------------------------+----------------------+----------+
| **POST**   | \servers\{id}\               | 4                    | minute   |
|            |  os-virtual-interfacesv2     |                      |          |
+------------+------------------------------+----------------------+----------+

You can also query the limits programmatically with a **GET**/limits call
for your account.

When a request exceeds the limits established for your account, a 413
HTTP response is returned with a ``Retry-After`` header that indicates
when you can attempt the request again.

.. _absolute-limits:

Absolute Limits
~~~~~~~~~~~~~~~

Absolute limits control the total number of specific objects that the
user can possess simultaneously.

Specify absolute limits to limit the overall number of items or amount
of capacity in the system. Absolute limits also include the amount of
resources currently consumed, which allow for programmatic visibility of
usage.

Specify absolute limits as name/value pairs.

The following ``max`` limits show the maximum amount of a resource that
can be used:

maxImageMeta: 40 The maximum number of metadata key value pairs associated with a particular image.

maxPersonality: 5 The maximum number of file path/content pairs that can be supplied on server build and rebuild.

maxPersonalitySize: 1000 The maximum size, in bytes, for each personality file.

maxServerMeta: 40 The maximum number of metadata key value pairs associated with a particular server.

maxTotalCores: -1 This limit is disabled, so no limits exist on the total number of cores.

maxTotalInstances: 100 The maximum number of Cloud Servers at any one time.

maxTotalPrivateNetworks: The maximum number of isolated networks that you can create. Set to 0 when Cloud Networks is disabled, 10 when Cloud Networks enabled.

maxTotalRAMSize: 131072 The maximum total amount of RAM (MB) of all Cloud Servers at any one time.

.. _get-limits:

Get Limits
~~~~~~~~~~

You can do a **GET**/limits call on a Cloud Servers endpoint to discover the
limits for your account. (http://api.rackspace.com/#compute_limits)

**Example: Image Reference in Create Server Request: JSON Request**

.. code::

    {
        "limits": {
            "absolute": {
                "maxImageMeta": 20, 
                "maxPersonality": 6, 
                "maxPersonalitySize": 10240, 
                "maxServerMeta": 20, 
                "maxTotalCores": -1, 
                "maxTotalFloatingIps": 5, 
                "maxTotalInstances": 100, 
                "maxTotalKeypairs": 100, 
                "maxTotalPrivateNetworks": 0, 
                "maxTotalRAMSize": 66560, 
                "maxTotalVolumeGigabytes": -1, 
                "maxTotalVolumes": 0, 
                "totalCoresUsed": 9, 
                "totalInstancesUsed": 3, 
                "totalKeyPairsUsed": 0, 
                "totalPrivateNetworksUsed": 0, 
                "totalRAMUsed": 16896, 
                "totalSecurityGroupsUsed": 0, 
                "totalVolumeGigabytesUsed": 0, 
                "totalVolumesUsed": 0
            }, 
            "rate": [
                {
                    "limit": [
                        {
                            "next-available": "2012-09-10T20:11:45.146Z", 
                            "remaining": 0, 
                            "unit": "DAY", 
                            "value": 0, 
                            "verb": "POST"
                        }, 
                        {
                            "next-available": "2012-09-10T20:11:45.146Z", 
                            "remaining": 0, 
                            "unit": "MINUTE", 
                            "value": 0, 
                            "verb": "GET"
                        }
                    ], 
                    "regex": "/v[^/]/(\\d+)/(rax-networks)/?.*", 
                    "uri": "/rax-networks"
                }, 
                {
                    "limit": [
                        {
                            "next-available": "2012-09-10T20:11:45.146Z", 
                            "remaining": 1000, 
                            "unit": "DAY", 
                            "value": 1000, 
                            "verb": "POST"
                        }
                    ], 
                    "regex": "/v[^/]/(\\d+)/(servers)/?.*", 
                    "uri": "/servers"
                }, 
                {
                    "limit": [
                        {
                            "next-available": "2012-09-10T20:11:45.146Z", 
                            "remaining": 100, 
                            "unit": "MINUTE", 
                            "value": 100, 
                            "verb": "ALL"
                        }
                    ], 
                    "regex": "/v[^/]/(\\d+)/?.*", 
                    "uri": "*"
                }
            ]
        }
    }


