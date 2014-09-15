"""Tests for otter.util.fp"""

from pyrsistent import m, v

from twisted.trial.unittest import SynchronousTestCase

from otter.util.fp import freeze, unfreeze
from otter.test.utils import matches

from testtools.matchers import Mismatch


class IsTypeAndValue(object):
    """testtools matcher that checks the type and the value."""

    def __init__(self, value):
        self.type = type(value)
        self.value = value

    def __str__(self):
        return 'IsTypeAndValue {} {}'.format(self.type, self.value)

    def match(self, value):
        """Ensure that matches type and equality."""
        if self.type is not type(value):
            return Mismatch("{} is not of type {}".format(
                type(value), self.type))
        if self.value != value:
            return Mismatch("expected {}, got {}".format(self.value, value))


def eqtype(v):
    """Return a 'matches' instance around IsTypeAndValue."""
    return matches(IsTypeAndValue(v))


class FreezeTests(SynchronousTestCase):
    """Tests for :obj:`freeze`."""

    def test_freeze_basic(self):
        """Non-dict and non-list objects are frozen to themselves."""
        self.assertEqual(freeze(1), 1)
        self.assertEqual(freeze('foo'), 'foo')

    def test_freeze_list(self):
        """Lists are frozen to :obj:`pyrsistent.PVector`s."""
        self.assertEqual(freeze([1, 2]), eqtype(v(1, 2)))

    def test_freeze_dict(self):
        """Dicts are frozen to :obj:`pyrsistent.PMap`s."""
        self.assertEqual(freeze({'a': 'b'}), eqtype(m(a='b')))

    def test_recurse_in_dictionary_values(self):
        """Dictionary values are recursively frozen."""
        self.assertEqual(freeze({'a': [1]}), eqtype(m(a=eqtype(v(1)))))

    def test_recurse_in_lists(self):
        """Values in lists are recursively frozen."""
        self.assertEqual(
            freeze(['a', {'b': 3}]),
            eqtype(v('a', eqtype(m(b=3)))))

    def test_recurse_in_tuples(self):
        """Values in tuples are recursively frozen."""
        self.assertEqual(freeze(('a', {})), ('a', eqtype(m())))


class UnfreezeTests(SynchronousTestCase):
    """Tests for :obj:`unfreeze`."""

    def test_unfreeze_basic(self):
        """Non-dict and non-list objects are unfrozen to themselves."""
        self.assertEqual(unfreeze(1), 1)
        self.assertEqual(unfreeze('foo'), 'foo')

    def test_unfreeze_list(self):
        """:obj:`pyrsistent.PVector`s are unfrozen to lists."""
        self.assertEqual(unfreeze(v(1, 2)), eqtype([1, 2]))

    def test_unfreeze_dict(self):
        """:obj:`pyrsistent.PMap`s are unfrozen to dicts."""
        self.assertEqual(unfreeze(m(a='b')), eqtype({'a': 'b'}))

    def test_recurse_in_dictionary_values(self):
        """PMap values are recursively unfrozen."""
        self.assertEqual(unfreeze(m(a=v(1))), eqtype({'a': eqtype([1])}))

    def test_recurse_in_lists(self):
        """Values in PVectors are recursively unfrozen."""
        self.assertEqual(
            unfreeze(v('a', m(b=3))),
            eqtype(['a', eqtype({'b': 3})]))

    def test_recurse_in_tuples(self):
        """Values in tuples are recursively unfrozen."""
        self.assertEqual(unfreeze(('a', m())), ('a', eqtype({})))
