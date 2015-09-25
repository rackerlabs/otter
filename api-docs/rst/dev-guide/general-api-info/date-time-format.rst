.. _date-time-format:

Date and time format
~~~~~~~~~~~~~~~~~~~~~~~~

For the display and consumption of date and time values, the Rackspace Autoscale service 
uses a date format that complies with ISO 8601.

The system time is expressed as UTC.


**Example: Autoscale date and time format**

.. code:: 

    yyyy-MM-dd'T'HH:mm:ssZ

For example, the UTC-5 format for May 19, 2013 at 8:07:08 a.m. is 

.. code::

    2013-05-19T08:07:08-05:00
    
The following table shows the date and time format codes.

**Table: Date and time format codes**

+------+-----------------------------------------------------------+
| yyyy | Four digit year                                           |
+======+===========================================================+
| MM   | Two digit month                                           |
+------+-----------------------------------------------------------+
| DD   | Two digit day                                             |
+------+-----------------------------------------------------------+
| T    | Separator for date/time                                   |
+------+-----------------------------------------------------------+
| HH   | Two digit hour (00-23)                                    |
+------+-----------------------------------------------------------+
| mm   | Two digit minute                                          |
+------+-----------------------------------------------------------+
| ss   | Two digit second                                          |
+------+-----------------------------------------------------------+
| Z    | RFC 8601 timezone (offset from GMT). If Z is not replaced |
|      | with the offset from GMT, it indicates a 00:00 offset.    |
+------+-----------------------------------------------------------+

