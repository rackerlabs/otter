"""
Module to parse a feed from AtomHopper
"""

from lxml import etree

_namespaces = {'atom': 'http://www.w3.org/2005/Atom'}


def parse(feed_data):
    """Get a tree from feed data

    :type feed_data: ``str``

    :return: an etree built from the feed data
    """
    return etree.fromstring(feed_data)


def xpath(path, elem):
    """Get a particular path from an etree

    :type path: ``str``
    :type elem: :class:`ElementTree` or :class:`Element`

    :return: whatever `lxml.xpath` would return based on the path, but
        should be used to obtain a list of :class:`Elements`
    """
    return etree.XPath(path, namespaces=_namespaces)(elem)


def entries(feed):
    """Get entries from a particular atom feed

    :type feed: :class:`ElementTree`

    :return: ``list`` of atom entry :class:`Elements`
    """
    return xpath('./atom:entry', feed)


def previous_link(feed):
    """Get the previous link from a particular AtomHopper feed

    :type feed: :class:`ElementTree`

    :return: the URL to the previous feed
    :rtype: ``str``
    """
    links = xpath('./atom:link[@rel="previous"]', feed)

    if len(links) == 0:
        return None

    return links[0].attrib['href']


def summary(entry):
    """Get the summary from a particular AtomHopper entry

    :type entry: :class:`Element`

    :return: the summary text
    :rtype: ``str``
    """
    summaries = xpath('./atom:summary', entry)

    if len(summaries) == 0:
        return None

    return summaries[0].text


def content(entry):
    """Get the text content from a particular AtomHopper entry

    :type entry: :class:`Element`

    :return: the content text
    :rtype: ``str``
    """
    contents = xpath('./atom:content', entry)

    if len(contents) == 0:
        return None

    return contents[0].text


def categories(entry, term_contains=None):
    """Get a list of categories for a particular AtomHopper entry

    :type entry: :class:`Element`

    :param term_contains: a particular pattern to match against categories
    :type term_contains: ``str``

    :return: the catagories of the entry that match ``term_contains``, or all
        categories if ``term_contains`` is None
    :rtype: ``str``
    """
    exp = './atom:category'
    if term_contains:
        exp += '[contains(@term, "{0}")]'.format(term_contains)

    return [x.attrib['term'] for x in xpath(exp, entry)]


def updated(entry):
    """Get the updated date/time as a string from a particular AtomHopper entry

    :type entry: :class:`Element`

    :return: the updated timestamp
    :rtype: ``str``
    """
    return xpath('./atom:updated', entry)[0].text
