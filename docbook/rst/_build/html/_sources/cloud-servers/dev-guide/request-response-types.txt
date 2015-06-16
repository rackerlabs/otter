======================
Request/Response Types
======================

API v2 supports JSON request and response formats.

You specify the request format in the ``Content-Type`` header in the
request. This header is required for operations that have a request
body. The syntax for the ``Content-Type`` header is:

.. code::

    Content-Type: application/format

Where *``format``* is either ``json`` or ``xml``.

You specify the response format by using one of the following methods:

-  ``Accept`` header. The syntax for the ``Accept`` header is::

       Accept: application/format

   Where *``format``* is either ``json`` or ``xml``.

   Default is ``json``.

-  Query extension. Add an ``.xml`` or ``.json`` extension to the
   request URI. For example, the ``.xml`` extension in the following URI
   request specifies that the response body is returned in XML format:

   .. code::

      POST /v2/010101/servers.xml

If you do not specify a response format, JSON is the default.

If you specify conflicting formats in the ``Accept`` header and the
query extension, the format specified in the query extension takes
precedence. For example, if the query extension is ``.xml`` and the
``Accept`` header specifies ``application/json``, the response is
returned in XML format.

You can serialize a response in a different format from the request
format. These examples show a request
body in JSON format and a response body in XML format.

**Example: Request with Headers: JSON**

.. code::

    POST /v2/010101/servers HTTP/1.1
    Host: dfw.servers.api.rackspacecloud.com
    Content-Type: application/json
    Accept: application/xml
    X-Auth-Token: eaaafd18-0fed-4b3a-81b4-663c99ec1cbb


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


**Example: JSON Request with XML Query Extension for the Response**

.. code::

    POST /v2/010101/servers.xml HTTP/1.1
    Host: dfw.servers.api.rackspacecloud.com
    Content-Type: application/json
    X-Auth-Token: eaaafd18-0fed-4b3a-81b4-663c99ec1cbb


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


