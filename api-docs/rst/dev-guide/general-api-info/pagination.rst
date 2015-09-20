.. _pagination:

Pagination 
~~~~~~~~~~~~~

The Auto Scale API supports pagination of items that are returned in API
call responses. Pagination enables users to view all responses even if
the number of items returned in the response body is longer than what
fits on one page.

The pagination limit for the Auto Scale API is 100. This means you can
view 100 items at a time.

For example, if you want to get a list of all the scaling groups, and
there are more than 100 groups, you see the first 100 groups on one page
and then a link at the bottom of the page that takes you to the next
page, which contains the next 100 items.

A pagination limit that is set beyond 100 is defaulted to 100. And a
limit that is set to smaller than 1 is defaulted to 1.

The Auto Scale API paginates the following items:

-  scaling groups

-  scaling policies

-  webhooks

Use the ``limit`` and ``marker`` parameters to navigate the collection of items that are returned in the request.

- Limit is the maximum number of items that can be returned on one page. If the 
  client submits a request with a limit beyond the 100 items supported by Auto Scale, the response returns 
  the ``413 overLimit`` error code.  

- Marker is the ID of the last item in the previous list. Items are sorted by create time in descending 
  order. When a create time is not available, items are sorted by ID. If the request includes an invalid 
  ID, the response returns the``400 badRequest`` error code. 

..  note:: 
     The ``limit`` and ``marker`` parameters are optional.

Paginating group lists
^^^^^^^^^^^^^^^^^^^^^^^^

When you submit a request for a group manifest, you receive a list of
all the available scaling groups and associated policies. However, the
response body only lists 100, or whatever number of responses per page
you configure using the ``limit`` parameter. If there are more results
available than what you specified in the ``limit`` parameter, a ``next``
link is provided in the ``rel`` in the response body. This is shown in
the following example that sets the ``limit`` parameter value to ``2`` to list 
two responses per page.

.. code::

  $ curl -H "x-auth-token: ${AUTHTOKEN}" /
   https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups?limit=2 | python -m json.tool

 
**Example: Paginating group lists example**

.. code::  

    {
        "groups": [
            {
                "id": "1bb9d1e7-d7d2-4a87-baa3-8902fbfc8f02",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/1bb9d1e7-d7d2-4a87-baa3-8902fbfc8f02/",
                        "rel": "self"
                    }
                ],
                "state": {
                    "active": [],
                    "activeCapacity": 0,
                    "desiredCapacity": 0,
                    "name": "test_sgroup711740",
                    "paused": false,
                    "pendingCapacity": 0
                }
            },
            {
                "id": "d8a0ed6a-c1cd-4578-85e9-ebe88291791d",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/d8a0ed6a-c1cd-4578-85e9-ebe88291791d/",
                        "rel": "self"
                    }
                ],
                "state": {
                    "active": [],
                    "activeCapacity": 0,
                    "desiredCapacity": 0,
                    "name": "test_sgroup453884",
                    "paused": false,
                    "pendingCapacity": 0
                }
            }
        ],
        "groups_links": [
            {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/?limit=2&marker=d8a0ed6a-c1cd-4578-85e9-ebe88291791d",
                "rel": "next"
            }
        ]
    }
                                

For Auto Scale, the ``limit`` value range is ``1 - 100`` inclusive.
If you set the value to a number greater than 100, it defaults to ``100``. 
Set it to less tan 1, and it defaults to ``1``. 

If you provide an invalid query argument for ``limit``, the response returns a 
``400`` message. The ``marker`` parameter specifies the last seen
group ID. When you click on the link that is returned, all the groups
displayed will have group Ids that are greater than
``f82bb000-f451-40c8-9dc3-6919097d2f7e``.

Paginating policy lists
^^^^^^^^^^^^^^^^^^^^^^^^

When you submit a request to obtain all the policies associated with a
scaling group, a list of policies is returned. However, the response
body only lists 100, or whatever number of responses per page you
configure using the ``limit`` parameter. If there are more results
available than what you specified in the ``limit`` parameter, a ``next``
link is provided in the ``rel`` in the response body. This is shown in
the following example that sets the ``limit`` parameter value to ``2`` to list 
two responses per page.

.. code::

  $ curl -H "x-auth-token: ${AUTHTOKEN}"  \
  https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies?limit=2 | python -m json.tool


**Example: Paginating policy lists example**

.. code::  

    {
        "policies": [
            {
                "change": 10,
                "cooldown": 5,
                "id": "25adccf9-0077-4510-b37d-90a48c9dc08f",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/25adccf9-0077-4510-b37d-90a48c9dc08f/",
                        "rel": "self"
                    }
                ],
                "name": "scale up by 10",
                "type": "webhook"
            },
            {
                "args": {
                    "cron": "0 */2 * * *"
                },
                "change": 10,
                "cooldown": 3,
                "id": "2d321cd2-b873-4865-9941-5ea6783fd58c",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/2d321cd2-b873-4865-9941-5ea6783fd58c/",
                        "rel": "self"
                    }
                ],
                "name": "Schedule policy to run repeately",
                "type": "schedule"
            }
        ],
        "policies_links": [
            {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/?limit=2&marker=2d321cd2-b873-4865-9941-5ea6783fd58c",
                "rel": "next"
            }
        ]
    }
                                

The ``marker`` parameter points to the last seen policy ID. When you
click on the link that is returned, all the policies displayed will have
policy Ids that are greater than ``f82bb000-f451-40c8-9dc3-6919097d2f7e``.

Paginating webhook lists
^^^^^^^^^^^^^^^^^^^^^^^^^

When you submit a request to obtain all the webhooks associated with a
policy, a list of webhooks is returned. However, the response body only
lists 100, or whatever number of responses per page you configure using
the ``limit`` parameter. If there are more results available than what
you specified in the ``limit`` parameter, a ``next`` link is provided in
the ``rel`` in the response body. This is shown in
the following example that sets the ``limit`` parameter value to ``2`` to list 
two responses per page.

.. code::

   $ curl -H "x-auth-token: ${AUTHTOKEN}" \
    https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/25adccf9-0077-4510-b37d-90a48c9dc08f/webhooks?limit=2 | python -m json.tool

 
**Example: Paginating webhook lists example**

.. code::  

    {
        "webhooks": [
            {
                "id": "012d0b95-8185-4955-be00-cee9bc25d177",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/25adccf9-0077-4510-b37d-90a48c9dc08f/webhooks/012d0b95-8185-4955-be00-cee9bc25d177/",
                        "rel": "self"
                    },
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/execute/1/3ae6d5b89b471fd6ac2d8496e19bea1ae6e766c83869903de745bf7ae3fbfd45/",
                        "rel": "capability"
                    }
                ],
                "metadata": {},
                "name": "webhook3"
            },
            {
                "id": "a5aefc55-1ac8-41a0-8d70-7ee30f56af69",
                "links": [
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/25adccf9-0077-4510-b37d-90a48c9dc08f/webhooks/a5aefc55-1ac8-41a0-8d70-7ee30f56af69/",
                        "rel": "self"
                    },
                    {
                        "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/execute/1/ad1cad8361963cc350ac0f1fc4edd2cacc24e0d77eee03b8c0cfaf7feeec7ac3/",
                        "rel": "capability"
                    }
                ],
                "metadata": {},
                "name": "webhook1"
            }
        ],
        "webhooks_links": [
            {
                "href": "https://dfw.autoscale.api.rackspacecloud.com/v1.0/851153/groups/f3af279b-10d7-4a26-aead-98c00bff260f/policies/25adccf9-0077-4510-b37d-90a48c9dc08f/webhooks/?limit=2&marker=a5aefc55-1ac8-41a0-8d70-7ee30f56af69",
                "rel": "next"
            }
        ]
    }
                                

The ``marker`` parameter points to the last seen webhook ID. When you
click on the link that is provided in the response body, all the
webhooks displayed will have webhook Ids that are greater than
``f82bb000-f451-40c8-9dc3-6919097d2f7e``.
