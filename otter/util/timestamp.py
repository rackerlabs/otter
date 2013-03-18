"""
Utilities for consistently handling timestamp formats in otter
"""

from datetime import datetime
import iso8601


MIN = "{0}Z".format(datetime.min.isoformat())


def now():
    """
    :return: the current UTC time in ISO8601 zulu timestamp format
    """
    # utcnow returns a naive datetime object without tzinfo, which means that
    # when isoformat() is called no time zone info is included

    # however, python doesn't seem to do zulu format =/ so just add 'Z' to the
    # end
    return "{0}Z".format(datetime.utcnow().isoformat())


def from_timestamp(timestamp):
    """
    :param str timestamp: a timestamp string which is a ISO8601 formatted
        UTC date/timestamp, with a 'T' separator and Zulu timezone format,
        such as that produced by :func:`now` or :data:`MIN`

    :return: a timezone-aware ``datetime`` object
    """
    return iso8601.parse_date(timestamp)
