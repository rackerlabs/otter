==================================================
Efficient Polling with the Changes-Since Parameter
==================================================

You can poll for the status of certain operations by issuing a **GET**
request on various elements. Rather than re-downloading and re-parsing
the full status at each polling interval, you can use the
*``changes-since``* parameter to check for changes since a previous
request. The *``changes-since``* time is specified as an `ISO
8601 <http://en.wikipedia.org/wiki/ISO_8601>`__ dateTime
(2011-01-24T17:08Z).

The operations that use the *``changes-since``* filter are:

-  **GET** /servers

-  **GET** /servers/detail

-  **GET** /images

-  **GET** /images/detail

The format for the timestamp is::

    CCYY-MM-DDThh:mm:ss

Optionally, to return the time zone as an offset from UTC, append the
following:

.. code::

   ±hh:mm

If you omit the time zone (2011-01-24T17:08), the UTC time zone is
assumed.

If data has changed, only the items changed since the specified time are
returned in the response.

If date has not changed since the ``changes-since`` time, an empty
list is returned.

For example, issue a **GET** request against the following endpoint to
list all servers that have changed since Mon, 24 Jan 2011 17:08:00 UTC:

.. code::

   https://dfw.servers.api.rackspacecloud.com/v2/010101/servers?changes-since=2011-01-24T17:08:00Z

To enable you to keep track of changes, the ``changes-since`` filter
also displays images and servers that have been deleted provided that
the ``changes-since`` filter specifies a date in the last 30 days.
Items deleted more than 30 days ago might be returned, but it is not
guaranteed.

