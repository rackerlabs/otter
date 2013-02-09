import simplejson as json
import traceback
import logging
import socket
from twiggy.levels import name2level
from twiggy.lib import iso8601time, thread_name
import os

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
    
    def __copy__(self):
        return self.__class__(self.separator, self.traceback_prefix, self.conversion.copy())

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

    def get_full_message(self, exc_info):
        """
        Generates the value to be placed into the C{full_message} field - if
        exc_info is provided, will be the traceback.  If not, will be the empty
        string.

        @param exc_info: for example, the output of sys.exc_info()
        @type exc_info: C{tuple} of the exception type, exception value, and
            the traceback object.  Or C{None}

        @return: formatted traceback of the C{exc_info} it is provided, or the
            empty string if it is not
        @rtype: C{str}
        """
        if exc_info:
            return "\n".join(traceback.format_exception(*exc_info))
        return ''

    def make_message_dict(self, record):
        tbstr = record.traceback
        outrec = {
            'version': "1.0",
            'host': socket.gethostname(),
            'short_message': record.text,
            'full_message': self.add_extra_fields({},record.fields),
            'timestamp': iso8601time(record.fields["time"]),
            'level': self.convert_level_to_syslog(record.fields["level"]),
            'facility': self.facility,
            '_pid': os.getpid(),
            '_thread_name': thread_name()
            }
        if tbstr is not None:
            outrec['_traceback'] = traceback
            outrec['exception'] = record.text
            outrec['short_message'] = 'Exception'
        return outrec

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
        # record.processName was added in Python 2.6.2
        pn = getattr(record, 'processName', None)
        if pn is not None:
            message_dict['_process_name'] = pn

        # skip_list is used to filter additional fields in a log message.
        # It contains all attributes listed in
        # http://docs.python.org/library/logging.html#logrecord-attributes
        # plus exc_text, which is only found in the logging module source,
        # and id, which is prohibited by the GELF format.
        skip_list = (
            'level', 'time', '_time',
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'funcName', 'id', 'levelname', 'levelno', 'lineno', 'module',
            'msecs', 'msecs', 'message', 'msg', 'name', 'pathname', 'process',
            'processName', 'relativeCreated', 'request', 'thread', 'threadName')

        for key, value in record.items():
            # data can be full of locals and exception objects and craziness. Not all of it can be json.dump()ed
            if key == "data":
                value = self.fix_data(value)
            if key not in skip_list:
                message_dict['_%s' % key] = value

        return message_dict

json_format = JSONFormat()
