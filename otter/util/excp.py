"""
Exception related utilities
"""

import sys


def raise_to_exc_info(e):
    """Raise an exception, and get the exc_info that results."""
    try:
        raise e
    except type(e):
        return sys.exc_info()
