"""
Tests for :mod:`otter.indexer.atom`
"""

from twisted.trial.unittest import TestCase

from otter.test.utils import fixture

from otter.indexer.atom import (
    parse, summary, categories, entries, previous_link, updated, content
)


class SimpleAtomTestCase(TestCase):
    """
    Tests for the public functions in :mod:`otter.indexer.atom` against a
    simple atom feed fixture.
    """
    def setUp(self):
        """
        Load simple atom feed fixture
        """
        self.simple_atom = parse(fixture("simple.atom"))
        self.simple_entry = entries(self.simple_atom)[0]

    def test_parse(self):
        """
        :func:`otter.indexer.atom.parse` returns something with an xpath
        attribute.
        """
        self.assertEqual(hasattr(self.simple_atom, "xpath"), True)

    def test_summary(self):
        """
        :func:`otter.indexer.atom.summary` finds "compute.instance.update"
        as the summary of the first entry in the sample simple atom feed
        """
        self.assertEqual(
            summary(self.simple_entry),
            "compute.instance.update")

    def test_categories_with_pattern(self):
        """
        :func:`otter.indexer.categories` finds categories that match a
        particular pattern only, if pattern is given
        """
        self.assertEqual(
            categories(self.simple_entry, 'REGION='),
            ['REGION=dfw']
        )

    def test_categories(self):
        """
        :func:`otter.indexer.categories` finds all categories if no pattern
        is given
        """
        self.assertEqual(
            categories(self.simple_entry),
            ['REGION=dfw', 'DATACENTER=dfw1']
        )

    def test_previous_link(self):
        """
        :func:`otter.indexer.previous_link` finds the previous link in the
        simple sample atom feed.
        """
        self.assertEqual(
            previous_link(self.simple_atom),
            ('http://example.org/feed/?'
             'marker=urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a')
        )

    def test_updated(self):
        """
        :func:`otter.indexer.updated` finds the updated timestamp in the
        first entry in the sample simple atom feed
        """
        self.assertEqual(
            updated(self.simple_entry),
            '2003-12-13T18:30:02Z'
        )

    def test_content(self):
        """
        :func:`otter.indexer.content` finds "Hello." as the content in the
        first entry in the sample simple atom feed
        """
        self.assertEqual(
            content(self.simple_entry),
            'Hello.'
        )
