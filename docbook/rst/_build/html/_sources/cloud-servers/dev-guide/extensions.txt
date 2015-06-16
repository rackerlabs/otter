==========
Extensions
==========

The OpenStack Compute API is extensible and Rackspace has implemented
several extensions. You can list available extensions and get details for a
specific extension.

List Extensions
~~~~~~~~~~~~~~~

Applications can programmatically determine which extensions are
available by issuing a **GET** on the ``/extensions`` URI.

http://api.rackspace.com/#compute_extensions


Get Extension Details
~~~~~~~~~~~~~~~~~~~~~

You can also query extensions by their unique alias to determine if an
extension is available. An unavailable extension issues an itemNotFound
(404) response.

http://api.rackspace.com/#compute_extensions

Extended Responses and Actions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use extensions to define new data types, parameters, actions, headers,
states, and resources.

In XML, you can define additional elements and attributes. Define these
elements in the namespace for the extension.

In JSON, you must use the alias. The volumes element in the example is defined in the ``RS-CBS`` namespace.

Actions work in exactly the same manner as illustrated in the example.
Extended headers are always prefixed with ``X-`` followed by the alias
and a dash: (``X-RS-CBS-HEADER1``). You must prefix states and
parameters with the extension alias followed by a colon. For example, an
image can be in the ``RS-PIE:PrepareShare`` state.

.. important::
   Applications should be prepared to ignore response data that
   contains extension elements. An extended state should always be treated as
   an ``UNKNOWN`` state if the application does not support the extension.
   Applications should also verify that an extension is available before
   submitting an extended request.


**Example: Extended Server: JSON Response**

.. code::

    {
        "servers": [
            {
                "id": "52415800-8b69-11e0-9b19-734f6af67565",
                "tenant_id": "010101",
                "user_id": "MyRackspaceAcct",
                "name": "sample-server",
                "updated": "2010-10-10T12:00:00Z",
                "created": "2010-08-10T12:00:00Z",
                "hostId": "e4d909c290d0fb1ca068ffaddf22cbd0",
                "status": "BUILD",
                "progress": 60,
                "accessIPv4" : "67.23.10.132",
                "accessIPv6" : "::babe:67.23.10.132",
                "image" : {
                    "id": "52415800-8b69-11e0-9b19-734f6f006e54",
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/images/52415800-8b69-11e0-9b19-734f6f006e54"
                        },
                        {
                            "rel": "bookmark",
                            "href": "http://dfw.servers.api.rackspacecloud.com/010101/images/52415800-8b69-11e0-9b19-734f6f006e54"
                        }
                    ]
                },
                "flavor" : {
                    "id": "52415800-8b69-11e0-9b19-734f216543fd",
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/flavors/52415800-8b69-11e0-9b19-734f216543fd"
                        },
                        {
                            "rel": "bookmark",
                            "href": "http://dfw.servers.api.rackspacecloud.com/010101/flavors/52415800-8b69-11e0-9b19-734f216543fd"
                        }
                    ]
                },
                "addresses": {
                    "public" : [
                        {
                            "version": 4,
                            "addr": "67.23.10.132"
                        },
                        {
                            "version": 6,
                            "addr": "::babe:67.23.10.132"
                        },
                        {
                            "version": 4,
                            "addr": "67.23.10.131"
                        },
                        {
                            "version": 6,
                            "addr": "::babe:4317:0A83"
                        }
                    ],
                    "private" : [
                        {
                            "version": 4,
                            "addr": "10.176.42.16"
                        },
                        {
                            "version": 6,
                            "addr": "::babe:10.176.42.16"
                        }
                    ]
                },
                "metadata": {
                    "Server Label": "Web Head 1",
                    "Image Version": "2.1"
                },
                "links": [
                    {
                        "rel": "self",
                        "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/servers/52415800-8b69-11e0-9b19-734f6af67565"
                    },
                    {
                        "rel": "bookmark",
                        "href": "http://dfw.servers.api.rackspacecloud.com/010101/servers/52415800-8b69-11e0-9b19-734f6af67565"
                    }
                ],
                "RS-CBS:volumes": [
                    {
                        "name": "OS",
                        "href": "https://cbs.api.rackspacecloud.com/12934/volumes/19"
                    },
                    {
                        "name": "Work",
                        "href": "https://cbs.api.rackspacecloud.com/12934/volumes/23"
                    }
                ]
            }
        ]
    }


**Example: Extended Action: JSON Request**

.. code::

    {
        "RS-CBS:attach-volume": {
            "href" : "https://cbs.api.rackspacecloud.com/12934/volumes/19"
        }
    }


