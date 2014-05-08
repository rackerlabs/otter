"""
Tests for undo stacks.
"""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import Deferred
from twisted.internet.task import Cooperator

from otter.undo import IUndoStack
from otter.undo import InMemoryUndoStack


class InMemoryUndoStackTests(SynchronousTestCase):
    """
    Tests for the in memory undo stack.
    """
    def setUp(self):
        """
        Configure an empty stack.
        """
        def termination():
            return lambda: True

        def run_immediately(f):
            f()

        self.cooperator = Cooperator(
            terminationPredicateFactory=termination,
            scheduler=run_immediately)
        self.undo = InMemoryUndoStack(self.cooperator.coiterate)

    def test_provides_IUndoStack(self):
        """
        InMemoryUndoStack provides IUndoStack.
        """
        verifyObject(IUndoStack, self.undo)

    def test_push(self):
        """
        push puts an operation and it's arguments onto the stack.
        """
        calls = []

        def op(*args, **kwargs):
            calls.append((args, kwargs))

        self.undo.push(op, 'foo', bar='baz')

        self.undo.rewind()

        self.assertEqual(calls, [(('foo',), {'bar': 'baz'})])

    def test_rewind_in_reverse_order(self):
        """
        rewind invokes operations in the reverse of the order they are
        pushed onto the stack.  (Because it is a stack.)
        """
        calls = []

        def op(*args, **kwargs):
            calls.append((args, kwargs))

        self.undo.push(op, 'foo')
        self.undo.push(op, 'bar')
        self.undo.push(op, 'baz')

        self.undo.rewind()

        self.assertEqual(calls, [(('baz',), {}),
                                 (('bar',), {}),
                                 (('foo',), {})])

    def test_rewind_handles_deferreds(self):
        """
        rewind will wait on any deferreds returned by the undo operation
        function.
        """
        def op(op_d):
            return op_d

        op_d = Deferred()
        self.undo.push(op, op_d)

        d = self.undo.rewind()
        self.assertNoResult(d)

        op_d.callback(None)

        self.successResultOf(d)

    def test_rewind_blocks_on_deferreds_returned_by_ops(self):
        """
        rewind will serialize operations waiting on any deferreds returned
        before running the next operation.
        """
        called = [0]

        def op(op_d):
            called[0] += 1
            return op_d

        op_d1 = Deferred()
        self.undo.push(op, op_d1)
        op_d2 = Deferred()
        self.undo.push(op, op_d2)

        d = self.undo.rewind()
        self.assertEqual(called[0], 1)
        self.assertNoResult(d)

        op_d2.callback(None)
        self.assertEqual(called[0], 2)
        self.assertNoResult(d)

        op_d1.callback(None)
        self.successResultOf(d)

    def test_rewind_stops_on_error(self):
        """
        rewind errbacks it's completion deferred when it encounters an
        error.
        """
        called = [0]

        def op(op_d):
            called[0] += 1
            return op_d

        self.undo.push(op, None)

        op_d1 = Deferred()
        self.undo.push(op, op_d1)

        d = self.undo.rewind()
        self.assertNoResult(d)

        class DummyOpFailure(Exception):
            pass

        op_d1.errback(DummyOpFailure())
        self.assertEqual(called[0], 1)
        self.failureResultOf(d, DummyOpFailure)

    def test_rewind_empty_stack(self):
        """
        rewind completes successfully if the stack is empty.
        """
        self.successResultOf(self.undo.rewind())
