from itertools import chain
from urllib import quote


def append_segments(uri, *segments):
    """
    Append segments to URI in a reasonable way.

    :param str uri: base URI with or without a trailing /.
    :type segments: str or unicode
    :param segments: One or more segments to append to the base URI.

    :return: complete URI as str.
    """
    def _segments(segments):
        for s in segments:
            if isinstance(s, unicode):
                s = s.encode('utf-8')

            yield quote(s)

    uri = '/'.join(chain([uri.rstrip('/')], _segments(segments)))
    return uri
