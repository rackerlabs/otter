=====================
Paginated Collections
=====================

To reduce load on the service, list operations return a maximum number
of items at a time. The maximum number of items returned is
1000.

To navigate the collection, you can set the *``limit``* and *``marker``*
parameters in the URI request. For example:

.. code::

    ?limit=100&marker=1234

The *``marker``* parameter is the ID of the last item in the previous
list. Items are sorted by create time in descending order. When a create
time is not available, the items are sorted by ID. A marker with an ID
that is not valid returns an itemNotFound (404) fault.

The *``limit``* parameter sets the page size. If the client specifies a
*``limit``* value that is greater than the supported limit, an overLimit
(413) fault might be thrown.

Both parameters are optional.

.. note:: Paginated collections never return itemNotFound (404) faults when the
   collection is empty — clients should expect an empty collection.

For convenience, collections contain atom "next" links and can
optionally contain "previous" links. The last page in the collection
will not contain a "next" link.

The following examples show pages in a collection of images.

To get the first page, issue a **GET** request to the following endpoint
and set the *``limit``* parameter to the page size of a single item::

    http://dfw.servers.api.rackspacecloud.com/v2/010101/images?limit=1

Subsequent links honor the initial page size. A client can follow links
to traverse a paginated collection.

JSON Collection
~~~~~~~~~~~~~~~

In JSON, members in a paginated collection are stored in a JSON array
named after the collection. A JSON object can also hold members in cases
where using an associative array is more practical. Properties about the
collection itself, including links, are contained in an array with the
name of the entity an underscore (\_) and ``links``. The combination of
the objects and arrays that start with the name of the collection and an
underscore represent the collection in JSON.

This approach allows for extensibility of paginated collections by
allowing them to be associated with arbitrary properties. It also allows
collections to be embedded in other objects.

**Example: Images Collection – First Page: JSON**

.. code::

    {
        "images": [
            {
                "id": "52415800-8b69-11e0-9b19-734f6f006e54",
                "name": "CentOS 5.2",
                "links": [
                    {
                        "rel": "self",
                        "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/images/52415800-8b69-11e0-9b19-734f6f006e54"
                    }
                ]
            }
        ],
        "images_links" : [
            {
                "rel": "next",
                "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/images?limit=1&marker=52415800-8b69-11e0-9b19-734f6f006e54"
            }
        ]
    }


**Example: Images Collection – Second Page: JSON**

.. code::

    {
        "images" :  [
                {
                    "id" : "52415800-8b69-11e0-9b19-734f5736d2a2",
                    "name" : "My Server Backup",
                    "links": [
                        {
                            "rel" : "self",
                            "href" : "http://dfw.servers.api.rackspacecloud.com/v2/010101/images/52415800-8b69-11e0-9b19-734f5736d2a2"
                        }
                    ]
                }
            ],
        "images_links": [
            {
                "rel" : "next",
                "href" : "http://dfw.servers.api.rackspacecloud.com/v2/010101/images?limit=1&marker=52415800-8b69-11e0-9b19-734f5736d2a2"
            }
        ]
    }

| 

**Example: Images Collection – Last Page: JSON**

.. code::

    {
        "images": [
            {
                "id": "52415800-8b69-11e0-9b19-734f6ff7c475",
                "name": "Backup 2",
                "links": [
                    {
                        "rel": "self",
                        "href": "http://dfw.servers.api.rackspacecloud.com/v2/010101/images/52415800-8b69-11e0-9b19-734f6ff7c475"
                    }
                ]
            }
        ]
    }

