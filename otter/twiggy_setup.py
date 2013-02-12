""" Set up twiggy for the project """
import sys
from twiggy import addEmitters, outputs, levels
from otter.log.formatters import GELFFormat
from twisted.python import log as twlog
from twixxy import TwiggyLoggingObserver


def twiggy_setup():
    """ Set up twiggy for the project """
    std_output = outputs.StreamOutput(format=GELFFormat('otter'),
                                      stream=sys.stderr)

    addEmitters(
        # (name, min_level, filter, output),
        ("*", levels.DEBUG, None, std_output))

    observer = TwiggyLoggingObserver()
    twlog.startLoggingWithObserver(observer.emit)
