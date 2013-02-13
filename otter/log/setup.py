"""
Set up twiggy for the project
"""
import sys
from twiggy import addEmitters, outputs, levels, formats
from otter.log.formatters import GELFFormat

from twixxy import TwiggyLoggingObserver


def observer_factory():
    """
    Setup twiggy and return a twisted log observer.
    """
    std_output = outputs.StreamOutput(format=GELFFormat('otter'),
                                      stream=sys.stdout)

    addEmitters(
        # (name, min_level, filter, output),
        ("*", levels.DEBUG, None, std_output))

    observer = TwiggyLoggingObserver()
    return observer.emit

def observer_factory_debug():
    """
    Setup twiggy and return a twisted log observer.
    """
    std_output = outputs.StreamOutput(format=formats.line_format,
                                      stream=sys.stdout)

    addEmitters(
        # (name, min_level, filter, output),
        ("*", levels.DEBUG, None, std_output))

    observer = TwiggyLoggingObserver()
    return observer.emit
