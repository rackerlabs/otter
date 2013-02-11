import simplejson as json
import traceback
import logging
import socket
from twiggy.levels import name2level
from twiggy.lib import iso8601time, thread_name
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
        return repr(obj)


class JSONFormat(object):
    """This is a fork of GrayPy formatter. http://pypi.python.org/pypi/graypy """
    def __init__(self, facility = 'twisted', suffix = '\n\n'):
        self.suffix = suffix
        self.facility = facility
    
    def __call__(self, msg):
        message_dict = self.make_message_dict(msg)
        return json.dumps(message_dict, cls=ReprFallbackEncoder) + self.suffix

    def convert_level_to_syslog(self, level):
        return {
            name2level("CRITICAL"): 2,
            name2level("ERROR"): 3,
            name2level("WARNING"): 4,
            name2level("INFO"): 6,
            name2level("DEBUG"): 7,
        }.get(level, level)

    def make_message_dict(self, record):
        tbstr = record.traceback
        facility = self.facility
        if "name" in record.fields:
            facility = record.fields["name"]
        
        outrec = {
            'version': "1.0",
            'host': socket.gethostname(),
            'short_message': record.text,
            'timestamp': time.mktime(record.fields["time"]),
            'level': self.convert_level_to_syslog(record.fields["level"]),
            'facility': facility,
            '_pid': os.getpid(),
            '_thread_name': thread_name()
            }
        if tbstr is not None:
            outrec['_traceback'] = traceback
            outrec['full_message'] = record.text
            outrec['short_message'] = 'Exception'
        return self.add_extra_fields(outrec,record.fields)

    def fix_data(self, data):
        if not data:
            return data

        for k, v in data.iteritems():
            try:
                json.dumps(v)
            except Exception:
                data[k] = str(v)

        return data

    def add_extra_fields(self, message_dict, record):
        # skip_list is used to filter additional fields in a log message.
        skip_list = ('level', 'time', 'name', 'id')

        for key, value in record.items():
            # data can be full of locals and exception objects and craziness. Not all of it can be json.dump()ed
            if key == "data":
                value = self.fix_data(value)
            if key not in skip_list:
                message_dict['_%s' % key] = value

        return message_dict

json_format = JSONFormat()
