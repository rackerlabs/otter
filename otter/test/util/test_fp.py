"""Tests for otter.util.fp"""

from twisted.trial.unittest import SynchronousTestCase

from otter.util.fp import predicate_all


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
