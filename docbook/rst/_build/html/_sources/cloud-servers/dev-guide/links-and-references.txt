====================
Links and References
====================

Resources often need to refer to other resources. For example, when you
create a server, you must specify the image from which to build the
server. You can specify the image by providing an ID or a URL to a
remote image. When you provide an ID for a resource, it is assumed that
the resource exists in the current endpoint.

**Example: Image Reference in Create Server Request: JSON Request**

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
                    "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBpdCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5kIGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVsc2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4gQnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRoZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlvdSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vyc2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6b25zLiINCg0KLVJpY2hhcmQgQmFjaA=="
                }
            ],
            "networks": [
                {
                     "uuid": "4ebd35cf-bfe7-4d93-b0d8-eb468ce2245a"
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

.. code::

    {
        "server": {
            "name": "new-server-test",
            "image": "52415800-8b69-11e0-9b19-734f6f006e54",
            "flavor": "52415800-8b69-11e0-9b19-734f1195ff37",
            "metadata": {
                "My Server Name": "Apache1"
            },
            "personality": [
                {
                    "path": "/etc/banner.txt",
                    "contents": "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6 b25zLiINCg0KLVJpY2hhcmQgQmFjaA=="
                }
            ]
        }
    }


**Example: Full Image Reference in Create Server Request: JSON
Request**

.. code::

    {
        "server" : {
            "name" : "myUbuntuServer",
            "imageRef" : "https://dfw.servers.api.rackspacecloud.com/v2/010101/images/3afe97b2-26dc-49c5-a2cc-a2fc8d80c001",
            "flavorRef" : "6",
            "metadata" : {
                "My Server Name" : "Ubuntu 11.10 server"
            },
            "personality" : [
                {
                    "path" : "/etc/banner.txt",
                    "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBpdCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5kIGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVsc2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4gQnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRoZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlvdSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vyc2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6b25zLiINCg0KLVJpY2hhcmQgQmFjaA==" 
                }
            ],
            "networks": [
                {
                     "uuid": "4ebd35cf-bfe7-4d93-b0d8-eb468ce2245a"
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

.. code::

    {
        "server" : {
            "name" : "new-server-test",
            "imageRef" : "http://servers.api.openstack.org/1234/images/52415800-8b69-11e0-9b19-734f6f006e54",
            "flavorRef" : "52415800-8b69-11e0-9b19-734f1195ff37",
            "metadata" : {
                "My Server Name" : "Apache1" 
            },
            "personality" : [
                {
                    "path" : "/etc/banner.txt",
                    "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBpdCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5kIGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVsc2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4gQnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRoZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlvdSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vyc2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6b25zLiINCg0KLVJpY2hhcmQgQmFjaA=="
                } 
            ] 
        }
    }

For convenience, resources contain links to themselves. This allows a
client to easily obtain resource URIs rather than to construct them. The
following kinds of link relations are associated with resources:

-  ``self``. Contains a versioned link to the resource. Use these links
   when the link will be followed immediately.

-  ``bookmark``. Provides a permanent link to a resource that is
   appropriate for long-term storage.

-  ``alternate``. Contains an alternate representation of the resource.
   For example, a Cloud Servers image might have an alternate
   representation in the Cloud Servers image service.

In the following examples, the ``rel`` attribute shows the type of
representation to expect when following the link.

**Example: Server with Self Links: JSON**

.. code::

    {
        "server" : {
            "id" : "52415800-8b69-11e0-9b19-734fcece0043",
            "name" : "my-server",
            "links": [
                {
                    "rel" : "self",
                    "href" : "http://dfw.servers.api.rackspacecloud.com/v2/010101/servers/52415800-8b69-11e0-9b19-734fcece0043"
                },
                {
                    "rel" : "bookmark",
                    "href" : "http://dfw.servers.api.rackspacecloud.com/010101/servers/52415800-8b69-11e0-9b19-734fcece0043"
                }
            ]
        }
    }



**Example: Server with Alternate Link: JSON**

.. code::

    {
        "image" : {
            "id" : "52415800-8b69-11e0-9b19-734f5736d2a2",
            "name" : "My Server Backup",
            "links": [
                {
                    "rel" : "self",
                    "href" : "http://dfw.servers.api.rackspacecloud.com/v2/010101/images/52415800-8b69-11e0-9b19-734f5736d2a2"
                },
                {
                    "rel" : "bookmark",
                    "href" : "http://dfw.servers.api.rackspacecloud.com/010101/images/52415800-8b69-11e0-9b19-734f5736d2a2"
                },
                {
                    "rel"  : "alternate",
                    "type" : "application/vnd.openstack.image",
                    "href" : "http://glance.api.rackspacecloud.com/010101/images/52415800-8b69-11e0-9b19-734f5736d2a2"
                }
            ]
        }
    }

