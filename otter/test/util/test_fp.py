"""Tests for otter.util.fp"""

from effect import Effect, sync_perform

from twisted.trial.unittest import SynchronousTestCase

from otter.util.fp import (
    ERef, ModifyERef, ReadERef, eref_dispatcher, predicate_all, predicate_any)


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


class ERefTests(SynchronousTestCase):
    """Tests for :obj:`ERef`."""

    def test_read(self):
        """``read`` returns an Effect that represents the current value."""
        ref = ERef('initial')
        self.assertEqual(ref.read(), Effect(ReadERef(eref=ref)))

    def test_modify(self):
        """``modify`` returns an Effect that represents modification."""
        ref = ERef(0)
        transformer = lambda x: x + 1
        eff = ref.modify(transformer)
        self.assertEqual(eff,
                         Effect(ModifyERef(eref=ref, transformer=transformer)))

    def test_perform_read(self):
        """Performing the reading results in the current value."""
        ref = ERef('initial')
        result = sync_perform(eref_dispatcher, ref.read())
        self.assertEqual(result, 'initial')

    def test_perform_modify(self):
        """
        Performing the modification results in transforming the current value,
        and also returns the new value.
        """
        ref = ERef(0)
        transformer = lambda x: x + 1
        result = sync_perform(eref_dispatcher, ref.modify(transformer))
        self.assertEqual(result, 1)
        self.assertEqual(sync_perform(eref_dispatcher, ref.read()),
                         1)
