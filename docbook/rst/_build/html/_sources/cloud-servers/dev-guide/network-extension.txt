=================
Network extension
=================

Cloud Networks lets you create a virtual Layer 2 network, known as an
isolated network, which gives you greater control and security when you
deploy web applications.

When you create a next generation Cloud Server, Cloud Networks enables
you to attach one or more networks to your server. You can attach an
isolated network that you have created or a Rackspace network.

If you install the Cloud Networks virtual interface extension, you can
create a virtual interface to a specified Rackspace or isolated network
and attach that network to an existing server instance. You can also
list virtual interfaces for and delete virtual interfaces from a server
instance. For information about the Cloud Networks virtual interface
extension, see :ref:`cloud-networks-virtual-interface-extension`.

Cloud Networks enables you to attach one or more of the following
networks to your server:

*  **PublicNet**. Provides access to the Internet, Rackspace services
   such as Cloud Monitoring, Managed Operations Service Level Support,
   RackConnect, Cloud Backup, and certain operating system updates.

   When you list networks through Cloud Networks, PublicNet is labeled
   ``public``.

*  **ServiceNet**. Provides access to Rackspace services such as Cloud
   Files, Cloud Databases, and Cloud Backup, and to certain packages and
   patches through an internal only, multi-tenant network connection
   within each Rackspace data center.

   When you list networks through Cloud Networks, ServiceNet is labeled
   ``private``.

   You can use ServiceNet for communications among web servers,
   application servers, and database servers without incurring bandwidth
   charges. However, without an isolated network, you must apply
   security rules to protect data integrity. When you add or remove a
   server, you must update the security rules on individual servers to
   permit or deny connections from newly added servers or removed
   servers.

*  **Isolated**. Enables you to deploy web applications on a virtual
   Layer 2 network that you create through Cloud Networks. Keeps your
   server separate from PublicNet, ServiceNet, or both. When you create
   a isolated network, it is associated with your tenant ID.

.. _cloud-networks-virtual-interface-extension:

Cloud Networks Virtual Interface Extension
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the Cloud Networks virtual interface extension to create a virtual
interface to a specified network and attach that network to an existing
server instance. You can attach an isolated network that you have
created or a Rackspace network.

A virtual interface works in the same way as the network interface card
(NIC) inside your laptop. Like a NIC, a virtual interface is the medium
through which you can attach a network. To use a virtual interface to
attach a network to your server, you create and connect a virtual
interface for a specified network to a server instance. The network,
which is comprised of logical switches, is attached to your server
instance through the virtual interface.

You can create a maximum of one virtual interface per instance per
network.

You can also use the Cloud Networks virtual interface extension to:

*  List the virtual interfaces for a server instance.

*  Delete a virtual interface for a network from a server instance. When
   you delete a virtual interface, the associated network is detached
   from the server instance.

   If you want to delete an isolated network, the network cannot be
   attached to any server. Delete the virtual interface for the isolated
   network, and then you can delete the network.

Networks
~~~~~~~~

This section describes the API operations for the networks extension.

Networks
^^^^^^^^

**GET**/os-networksv2
   Lists the networks configured for a specified tenant ID.

**POST**/os-networksv2
   Creates a network for the specified tenant ID.

**POST**/os-networksv2
   Provisions a new server and attaches networks.

**GET**/os-networksv2/*``id``*
   Shows information for a specified network ID.

**DELETE**/os-networksv2/*``id``*
   Deletes the specified network.

List Networks
'''''''''''''

**GET**/os-networksv2
   Lists the networks configured for a specified tenant ID.
   Normal Response Code: OK (200)

   Error Response Codes: Unauthorized (401), Forbidden (403)

   Lists the networks configured for the tenant ID specified in the request
   URI.

   This operation does not require a request body.

   This operation returns a response body. The response body returns the
   following fields:

**Table: List Networks Response Fields**

+----------------+-----------------------------------------------------------+
| Name           | Description                                               |
+================+===========================================================+
| id             | The network ID.                                           |
+----------------+-----------------------------------------------------------+
| label          | The name of the network. ServiceNet is labeled as         |
|                | ``private`` and PublicNet is labeled as ``public`` in the |
|                | network list.                                             |
+----------------+-----------------------------------------------------------+
| cidr           | The CIDR for an isolated network.                         |
+----------------+-----------------------------------------------------------+

.. note::
   To list the networks that are associated with servers, see List
   Servers in the *Next Generation Cloud Servers Developer Guide*.

The following example shows a JSON response for the list networks operation.

**Example: List Networks: JSON Response**

.. code::

    {
       "networks":[
          {
             "cidr":"192.168.0.0/24",
             "id":"1f84c238-b05a-4374-a0cb-aa6140032cd1",
             "label":"new_network"
          },
          {
             "id":"00000000-0000-0000-0000-000000000000",
             "label":"public"
          },
          {
             "id":"11111111-1111-1111-1111-111111111111",
             "label":"private"
          }
       ]
    }


Create Network
''''''''''''''

**POST**/os-networksv2
   Creates a network for the specified tenant ID.
   Normal Response Code: OK (200)

   Error Response Codes: Bad Request (400), Unauthorized (401), Forbidden
   (403)

   This operation creates a network for the specified tenant ID.

   This operation requires a request body. Specify the following attributes
   in the request body:

**Table: Create Network Request Attributes**

+----------------+----------------------------------------------------+-------+
| Name           | Description                                        | Req?  |
+================+====================================================+=======+
| cidr           | The IP block from which to allocate the network.   | Yes   |
|                | For example, **``172.16.0.0/24``** or              |       |
|                | **``2001:DB8::/64``**. For more information about  |       |
|                | CIDR notation, see `*CIDR                          |       |
|                | Notation* <http://www.rackspace.com/knowledge_cent |       |
|                | er/article/using-cidr-notation>`__.                |       |
+----------------+----------------------------------------------------+-------+
| label          | The name of the new network. For example,          | Yes   |
|                | **``my_new_network``**.                            |       |
+----------------+----------------------------------------------------+-------+

This operation returns a response body. The response body returns the
following fields:


**Table: Create Network Response Fields**

+----------------+-----------------------------------------------------------+
| Name           | Description                                               |
+================+===========================================================+
| cidr           | The IP block from which the network was allocated.        |
+----------------+-----------------------------------------------------------+
| id             | The network ID.                                           |
+----------------+-----------------------------------------------------------+
| label          | The name of the new network.                              |
+----------------+-----------------------------------------------------------+

The following example shows a JSON request and response for the create network
operation.

**Example: Create Network: JSON Request**

.. code::

    {
        "network": 
            {
                "cidr": "192.168.0.0/24", 
                "label": "superprivate"
            }
    }

**Example: Create Network: JSON Response**

.. code::

    {
        "network": {
            "cidr": "192.168.0.0/24", 
            "id": "1ff4489e-db0e-45a6-8c9f-4616c6ef5db1", 
            "label": "superprivate"
        }
    }

Provision Server and Attach Networks
''''''''''''''''''''''''''''''''''''

**POST**/servers
   Provisions a new server with specified networks.
   Normal Response Code: Accepted (202)

   Error Response Codes: computeFault (400, 500, …), Bad Request (400),
   Unauthorized (401), Forbidden (403), Not Found (404), Bad Method (405),
   Request Entity Too Large (413), Unsupported Media Type (415), Service
   Unavailable (503)

+--------------------------------------+--------------------------------------+
| Status Transition:                   | ``BUILD``                            |
|                                      | ``ACTIVE``                           |
+--------------------------------------+--------------------------------------+
|                                      | ``BUILD``                            |
|                                      | ``ERROR`` (on error)                 |
+--------------------------------------+--------------------------------------+

This operation asynchronously provisions a new server.

You must specify the networks that you want to attach to your server. If
you do not specify any networks, ServiceNet and PublicNet are attached
by default.

You can optionally provision the server instance with specified isolated
networks. However, if you specify an isolated network, you must
explicitly specify the UUIDs for PublicNet and ServiceNet to attach
these networks to your server. The UUID for ServiceNet is
``11111111-1111-1111-1111-111111111111``, and the UUID for PublicNet is
``00000000-0000-0000-0000-000000000000``. Omit these UUIDs from the
request to detach from these networks.

.. note::
   Rack Connect and Managed Operations Service Level customers will receive
   an error if they opt out of attaching to PublicNet or ServiceNet.

To attach a network to an existing server, you must create a virtual
interface. See :ref:`virtual-interfaces`.

For complete information about this API operation, see `Create
Server` in the *Next Generation Cloud Servers Developer Guide*.

.. note::
   To list the networks that are associated with servers, see `List
   Servers` in the *Next Generation Cloud Servers Developer Guide*.

The following table describes the required and optional attributes that
you can specify in the request body:

**Table: Provision Server with Isolated Network Request Attributes**

+----------------+----------------------------------------------------+-------+
| Name           | Description                                        | Req.? |
+================+====================================================+=======+
| name           | The server name.                                   | Yes   |
+----------------+----------------------------------------------------+-------+
| imageRef       | The image reference. Specify as an ID or full URL. | Yes   |
+----------------+----------------------------------------------------+-------+
| flavorRef      | The flavor reference. Specify as an ID or full     | Yes   |
|                | URL.                                               |       |
+----------------+----------------------------------------------------+-------+
| networks       | By default, the server instance is provisioned     | No    |
|                | with all Rackspace networks and isolated networks  |       |
|                | for the tenant. Optionally, to provision the       |       |
|                | server instance with a specific isolated tenant    |       |
|                | network, specify the UUID of the network in the    |       |
|                | **uuid** attribute. You can specify multiple       |       |
|                | UUIDs.                                             |       |
+----------------+----------------------------------------------------+-------+
| OS-DCF:diskCon | The disk configuration value, which is ``AUTO`` or | No    |
| fig            | ``MANUAL``. See `Disk Configuration                |       |
|                | Extension <http://docs.rackspace.com/servers/api/v |       |
|                | 2/cs-devguide/content/ch_extensions.html>`__.      |       |
+----------------+----------------------------------------------------+-------+
| metadata       | Metadata key and value pairs.                      | No    |
+----------------+----------------------------------------------------+-------+
| personality    | File path and contents.                            | No    |
+----------------+----------------------------------------------------+-------+

The following example shows a JSON request and response for the provision
server operation.

**Example: Provision Server with Isolated Network: JSON Request**

.. code::

    {
        "server" : {
            "name" : "api-test-server-1",
            "imageRef" : "3afe97b2-26dc-49c5-a2cc-a2fc8d80c001",
            "flavorRef" : "2",
            "config_drive": true,
            "key_name":"name_of_keypair",
            "OS-DCF:diskConfig" : "AUTO",
            "metadata" : {
                "My Server Name" : "API Test Server 1" 
            },
            "personality" : [
                {
                    "path" : "/etc/banner.txt",
                    "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6 b25zLiINCg0KLVJpY2hhcmQgQmFjaA==" 
                }
            ],
            "networks": [
                {
                     "uuid": "f212726e-6321-4210-9bae-a13f5a33f83f"
                }, 
                {
                     "uuid": "00000000-0000-0000-0000-000000000000"
                }, 
                {
                     "uuid": "11111111-1111-1111-1111-111111111111"
                } 
            ]
        }
    }

**Example: Provision Server with Isolated Network: JSON Response**

.. code::

    {
        "server": {
            "OS-DCF:diskConfig": "AUTO", 
            "adminPass": "LMoheHauXt8w", 
            "id": "ef08aa7a-b5e4-4bb8-86df-5ac56230f841", 
            "links": [
                {
                    "href": "https://dfw.servers.api.rackspacecloud.com/v2/010101/servers/ef08aa7a-b5e4-4bb8-86df-5ac56230f841", 
                    "rel": "self"
                }, 
                {
                    "href": "https://dfw.servers.api.rackspacecloud.com/010101/servers/ef08aa7a-b5e4-4bb8-86df-5ac56230f841", 
                    "rel": "bookmark"
                }
            ]
        }
    }


Show Network
''''''''''''

**GET**/os-networksv2/*``id``*
   Shows information for a specified network ID.
   Normal Response Code: OK (200)

   Error Response Codes: Unauthorized (401), Forbidden (403), Network Not
   Found (420)

   Specify the network ID as *``id``* in the URI.

   This operation shows information for the specified network ID.

.. note::
   To list the networks that are associated with servers, see `List
   Servers` in the *Next Generation Cloud Servers Developer Guide*.

This operation does not require a request body.

This operation returns a response body. The response body returns the
following fields:

**Table: Show Network Response Fields**

+----------------+-----------------------------------------------------------+
| Name           | Description                                               |
+================+===========================================================+
| cidr           | The *CIDR* for an isolated private network.               |
+----------------+-----------------------------------------------------------+
| id             | The network ID.                                           |
+----------------+-----------------------------------------------------------+
| label          | The name of the network.                                  |
+----------------+-----------------------------------------------------------+


The following example shows a JSON response for the show
network operation.

**Example: Show Network: JSON Response**

.. code::

    {
        "network": {
            "cidr": "192.168.0.0/24", 
            "id": "f212726e-6321-4210-9bae-a13f5a33f83f", 
            "label": "superprivate_xml"
        }
    }

Delete Network
''''''''''''''

**DELETE**/os-networksv2/*``id``*
   Deletes the specified network.
   Normal Response Code: Accepted (202)

   Error Response Codes: Bad Request (400), Unauthorized (401), Forbidden
   (403), Network Not Found (404)

   This operation deletes the network specified in the URI.

   You cannot delete an isolated network unless the network is not attached
   to any server.

To detach a network from a server, delete the virtual interface for the
network from the server instance. See ref:`delete-virtual-interface`.

This operation does not require a request body.

This operation does not return a response body.

.. _virtual-interfaces:

Virtual Interfaces
^^^^^^^^^^^^^^^^^^

Use the Cloud Networks virtual interface extension to create a virtual
interface to a specified network and attach that network to an existing
server instance. You can attach a an isolated network that you have
created or a Rackspace network.

A virtual interface works in the same way as the network interface card
(NIC) inside your laptop. Like a NIC, a virtual interface is the medium
through which you can attach a network. To use a virtual interface to
attach a network to your server, you create and connect a virtual
interface for a specified network to a server instance. The network,
which is comprised of logical switches, is attached to your server
instance through the virtual interface.

You can create a maximum of one virtual interface per instance per
network.

You can also use the Cloud Networks virtual interface extension to:

*  List the virtual interfaces for a server instance.

*  Delete a virtual interface and detach it from a server instance.

**GET**/servers/*``instance_id``*/os-virtual-interfacesv2
   Lists the virtual interfaces configured for a server instance.

**POST**/servers/*``instance_id``*/os-virtual-interfacesv2
   Creates a virtual interface for a network and attaches the network to a
   server instance.

**DELETE**/servers/*``instance_id``*/os-virtual-interfacesv2/*``interface_id``*
   Deletes a virtual interface from a server instance.

.. _list-virtual-interfaces:

List Virtual Interfaces
'''''''''''''''''''''''

**GET**/servers/*``instance_id``*/os-virtual-interfacesv2
   Lists the virtual interfaces configured for a server instance.
   Normal Response Code: OK (200)

   Error Response Codes: Unauthorized (401), Forbidden (403)

Lists the virtual interfaces configured for a server instance.

Specify the server instance ID as *``instance_id``* in the URI.

This operation does not require a request body.

This operation returns a response body. The response body returns the
following fields:

**Table: List Virtual Interfaces Response Fields**

+----------------+-----------------------------------------------------------+
| Name           | Description                                               |
+================+===========================================================+
| id             | The virtual interface ID.                                 |
+----------------+-----------------------------------------------------------+
| ip\_addresses  | For each IP address associated with the virtual           |
|                | interface, lists the address, network ID, and network     |
|                | label.                                                    |
+----------------+-----------------------------------------------------------+
| mac\_address   | The Media Access Control (MAC) address for the virtual    |
|                | interface. A MAC address is a unique identifier assigned  |
|                | to network interfaces for communications on the physical  |
|                | network segment.                                          |
+----------------+-----------------------------------------------------------+

The following example shows a JSON response for the list virtual interfaces
operation.


**Example: List Virtual Interfaces: JSON Response**

.. code::

    {
        "virtual_interfaces": [
            {
                "id": "a589b11b-cd51-4274-8ec0-832ce799d156", 
                "ip_addresses": [
                    {
                        "address": "2001:4800:7810:0512:d87b:9cbc:ff04:850c", 
                        "network_id": "ba122b32-dbcc-4c21-836e-b701996baeb3", 
                        "network_label": "public"
                    }, 
                    {
                        "address": "64.49.226.149", 
                        "network_id": "ba122b32-dbcc-4c21-836e-b701996baeb3", 
                        "network_label": "public"
                    }
                ], 
                "mac_address": "BC:76:4E:04:85:0C"
            }, 
            {
                "id": "de7c6d53-b895-4b4a-963c-517ccb0f0775", 
                "ip_addresses": [
                    {
                        "address": "192.168.0.2", 
                        "network_id": "f212726e-6321-4210-9bae-a13f5a33f83f", 
                        "network_label": "superprivate_xml"
                    }
                ], 
                "mac_address": "BC:76:4E:04:85:20"
            }, 
            {
                "id": "e14e789d-3b98-44a6-9c2d-c23eb1d1465c", 
                "ip_addresses": [
                    {
                        "address": "10.181.1.30", 
                        "network_id": "3b324a1b-31b8-4db5-9fe5-4a2067f60297", 
                        "network_label": "private"
                    }
                ], 
                "mac_address": "BC:76:4E:04:81:55"
            }
        ]
    }

Create Virtual Interface
''''''''''''''''''''''''

**POST**/servers/*``instance_id``*/os-virtual-interfacesv2
   Creates a virtual interface for a network and attaches the network to a
   server instance.
   Normal Response Code: OK (200)

   Error Response Codes: Bad Request (400), Unauthorized (401), Forbidden (403)

This operation creates a virtual interface for a network and attaches
the network to a server instance.

Specify the server instance ID as *``instance_id``* in the URI.

Specify the network ID in the request body.

You can create a maximum of one virtual interface per instance per
network.

This operation requires a request body. Specify the following attributes
in the request body:

**Table: Create Virtual Interface Request Attributes**

+----------------+----------------------------------------------------+-------+
| Name           | Description                                        | Req.? |
+================+====================================================+=======+
| network\_id    | The ID of the network for which you want to create | Yes   |
|                | a virtual interface. You can create a virtual      |       |
|                | interface for an isolated or Rackspace network.    |       |
+----------------+----------------------------------------------------+-------+

This operation returns a response body. The response body returns the
following fields:

**Table: Create Virtual Interface Response Fields**

+----------------+-----------------------------------------------------------+
| Name           | Description                                               |
+================+===========================================================+
| mac\_address   | The Media Access Control (MAC) address for the virtual    |
|                | interface. A MAC address is a unique identifier assigned  |
|                | to network interfaces for communications on the physical  |
|                | network segment.                                          |
+----------------+-----------------------------------------------------------+
| id             | The virtual interface ID.                                 |
+----------------+-----------------------------------------------------------+
| ip\_addresses  | For each IP address associated with the virtual           |
|                | interface, lists the following information:               |
|                |                                                           |
|                | .. raw:: html                                             |
|                |                                                           |
|                |    <div class="itemizedlist">                             |
|                |                                                           |
|                | -  address. The IP address.                               |
|                |                                                           |
|                | -  network ID. The ID for the associated network.         |
|                |                                                           |
|                | -  network label. The label for the associated network.   |
|                |                                                           |
|                | .. raw:: html                                             |
|                |                                                           |
|                |    </div>                                                 |
+----------------+-----------------------------------------------------------+


The following examples show a JSON request and response for the create virtual
interface operation.

**Example: Create Virtual Interface: JSON Request**

.. code::

    {
       "virtual_interface": 
        {
          "network_id": "1f7920d3-0e63-4fec-a1cb-f7916671e8eb"
        }
    }

**Example: Create Virtual Interface: JSON Response**

.. code::

    {
       "virtual_interfaces":[
          {
             "mac_address":"FE:ED:FA:00:08:93",
             "id":"045f195f-3347-487b-8e80-8ee3390eda56",
             "ip_addresses":[
                {
                   "address":"192.168.0.1",
                   "network_id":"196a0246-86cc-46fa-9ecf-850f67c2cb7c",
                   "network_label":"added_network"
                }
             ]
          }
       ]
    }

.. _delete-virtual-interface:

Delete Virtual Interface
''''''''''''''''''''''''

**DELETE**/servers/*``instance_id``*/os-virtual-interfacesv2/*``interface_id``*
   Deletes a virtual interface from a server instance.
   Normal Response Code: OK (200)

   Error Response Codes: Bad Request (400), Unauthorized (401), Forbidden
   (403), Network Not Found (404)

This operation deletes the specified virtual interface from the
specified server instance.

Specify the server instance ID as *``instance_id``* in the URI.

Specify the virtual interface ID as *``interface_id``* in the URI. To
find the ID of a virtual interface, issue the list virtual interfaces
API operation. See ref:`list-virtual-interfaces`.

This operation does not require a request body.

This operation does not return a response body.

