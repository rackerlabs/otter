import sys
from twiggy import addEmitters, outputs, levels, filters, formats, emitters # import * is also ok
from otter.log.formatters import json_format

def twiggy_setup():
    std_output = outputs.StreamOutput(format=json_format, stream=sys.stderr)
    
    addEmitters(
        # (name, min_level, filter, output),
        ("*", levels.DEBUG, None, std_output),
        )