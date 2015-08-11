"""Tests for otter.util.fp"""

from pyrsistent import pmap

from twisted.trial.unittest import SynchronousTestCase

from otter.util.fp import (
    assoc_obj, predicate_all, predicate_any, set_in)


class PredicateAllTests(SynchronousTestCase):
    """
    Tests for :func:`otter.util.fp.predicate_all`
    """

    def test_combines_predicates(self):
        """
        Combines many predicates and returns another predicate function after applying
        and operator
        """
        p1 = lambda a: a % 2 == 0
        p2 = lambda a: a % 3 == 0
        p3 = lambda a: a % 5 == 0
        p = predicate_all(p1, p2, p3)
        self.assertTrue(p(30))
        self.assertFalse(p(10))
        self.assertFalse(p(2))
        self.assertFalse(p(3))
        self.assertFalse(p(5))
        self.assertFalse(p(6))

    def test_combines_one(self):
        """
        Works with one arg also
        """
        self.assertTrue(predicate_all(lambda a: a % 2 == 0)(4))

    def test_multiple_args(self):
        """
        Works with multiple argument predicates
        """
        self.assertTrue(
            predicate_all(lambda a, b: a % 2 == 0 and b % 2 == 0,
                          lambda a, b: a % 3 == 0 and b % 3 == 0)(6, 12))

    def test_multiple_kw_args(self):
        """
        Works with multiple keyword argument predicates
        """
        self.assertTrue(
            predicate_all(
                lambda **k: k['a'] % 2 == 0 and k['b'] % 2 == 0,
                lambda **k: k['a'] % 3 == 0 and k['b'] % 3 == 0)(a=6, b=12))


class PredicateAnyTests(SynchronousTestCase):
    """
    Tests for :func:`otter.util.fp.predicate_any`
    """

    def test_combines_predicates(self):
        """
        Combine many predicates and returns another predicate
        function after applying or operator
        """
        p1 = lambda a: a % 2 == 0
        p2 = lambda a: a % 3 == 0
        p3 = lambda a: a % 5 == 0
        p = predicate_any(p1, p2, p3)
        self.assertTrue(p(2))
        self.assertTrue(p(3))
        self.assertTrue(p(5))
        self.assertTrue(p(30))
        self.assertFalse(p(7))
        self.assertFalse(p(11))

    def test_combines_one(self):
        """
        Succeed with one arg also.
        """
        self.assertTrue(predicate_any(lambda a: a % 2 == 0)(4))

    def test_multiple_args(self):
        """
        Succeed with multiple argument predicates.
        """
        self.assertTrue(
            predicate_any(lambda a, b: a % 2 == 0 and b % 2 == 0,
                          lambda a, b: a % 3 == 0 and b % 3 == 0)(2, 4))

    def test_multiple_kw_args(self):
        """
        Succeed with multiple keyword argument predicates.
        """
        self.assertTrue(
            predicate_any(
                lambda **k: k['a'] % 2 == 0 and k['b'] % 2 == 0,
                lambda **k: k['a'] % 3 == 0 and k['b'] % 3 == 0)(a=2, b=4))


class SetInTests(SynchronousTestCase):
    """
    Tests for :func:`otter.util.fp.set_in`
    """
    def test_insufficient_keys_raises_value_error(self):
        """
        If zero keys are passed, a :class:`ValueError` is raised.
        """
        self.assertRaises(ValueError, set_in, {1: 2}, (), None)

    def test_returns_new_pmap_given_pmap(self):
        """
        If a PMap is passed in, a new PMap is returned, and even the new value
        that was passed in gets frozen.
        """
        self.assertEquals(set_in(pmap({1: 2}), (1,), {1: 3}),
                          pmap({1: pmap({1: 3})}))

    def test_returns_new_pmap_given_dict(self):
        """
        If a dictionary is passed in, a new PMap is returned and the old
        dictionary is unaffected.
        """
        a = {1: 2}
        self.assertEquals(set_in(a, (1,), {1: 3}), pmap({1: pmap({1: 3})}))
        self.assertEquals(a, {1: 2})

    def test_creates_dictionaries(self):
        """
        Create dictionaries as needed, if the old dict didn't have them.
        """
        self.assertEquals(set_in({}, (1, 2, 3), 4),
                          pmap({1: pmap({2: pmap({3: 4})})}))


class AssocObjTests(SynchronousTestCase):
    """Tests for :func:`assoc_obj`."""

    def test_assoc(self):
        """
        Creates a new object that's a copy of the old one, with the
        specified attributes rebound. Existing attributes are identical.
        """
        class Foo(object):
            def __init__(self):
                self.l = [1, 2]
                self.name = "foo"

        o = Foo()
        new = assoc_obj(o, name="bar")
        self.assertEqual(o.name, "foo")
        self.assertEqual(new.name, "bar")
        self.assertIs(o.l, new.l)
