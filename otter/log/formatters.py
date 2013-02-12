"""JSON Formatters for GELF with Twiggy """
import json
import socket
from twiggy.levels import name2level
from twiggy.lib import thread_name
import os
import time


class ReprFallbackEncoder(json.JSONEncoder):
    """
    A JSONEncoder that will use the repr(obj) as the default serialization
    for objects taht the base JSONEncoder does not know about.

    This will ensure that even log messages that include unserializable objects
    (like from 3rd party libraries) will still have reasonable representations
    in the logged JSON and will actually be logged and not discarded by the
    logging system because of a formatting error.
    """
    def default(self, obj):
        """
        Serialize obj as repr(obj).
        """
        return repr(obj)


class GELFFormat(object):
    """
    A Twiggy log Format that produces https://github.com/Graylog2/graylog2-docs/wiki/GELF
    format messages.
    """
    def __init__(self, facility, suffix='\n'):
        self.suffix = suffix
        self.facility = facility

    def __call__(self, msg):
        """
        Twiggy uses callable to format messages.
        """
        message_dict = self._make_message_dict(msg)
        return json.dumps(message_dict, cls=ReprFallbackEncoder) + self.suffix

    def _convert_level_to_syslog(self, level):
        """
        Convert the level from Twiggy into a syslog appropriate level.
        """
        return {
            name2level("CRITICAL"): 2,
            name2level("ERROR"): 3,
            name2level("WARNING"): 4,
            name2level("INFO"): 6,
            name2level("DEBUG"): 7,
        }.get(level, level)

    def _make_message_dict(self, record):
        """
        Make a JSON serializable dict out of a record.
        """
        outrec = {
            'version': "1.0",
            'host': socket.gethostname(),
            'short_message': record.text,
            'timestamp': time.mktime(record.fields["time"]),
            'level': self._convert_level_to_syslog(record.fields["level"]),
            'facility': record.fields.get('name', self.facility),
            'full_message': record.traceback or '',
            '_pid': os.getpid(),
            '_thread_name': thread_name()
        }

        return self._add_extra_fields(outrec, record.fields)

    def _add_extra_fields(self, message_dict, record):
        """
        Add extra fields to an existing message dict,
        skipping clearly illegal arguments (e.g. id) and things that
        are being sent elsewhere (e.g. level, time, name) and also
        making sure that the data is serializable.
        """
        skip_list = ('level', 'time', 'name', 'id')

        for key, value in record.items():
            if key not in skip_list:
                message_dict['_%s' % key] = value

        return message_dict
