"""
Tests for :mod:`otter.log.intents`
"""

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    base_dispatcher,
    sync_perform)
from effect.testing import perform_sequence

import mock

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.log import log as default_log
from otter.log.intents import (
    err,
    get_fields,
    get_log_dispatcher,
    get_msg_time_dispatcher,
    merge_effectful_fields,
    msg,
    msg_with_time,
    with_log)
from otter.test.utils import (
    CheckFailureValue, IsBoundWith, matches, mock_log, raise_)


class LogDispatcherTests(SynchronousTestCase):
    """
    Tests to verify dispatcher returned from `get_log_dispatcher`
    performs logging
    """

    def setUp(self):
        self.log = mock_log()
        self.disp = ComposedDispatcher([
            get_log_dispatcher(self.log, {'f1': 'v'}), base_dispatcher])

    def test_boring(self):
        """
        Non log intents are performed
        """
        self.assertEqual(
            sync_perform(self.disp, Effect(Constant("foo"))), "foo")

    def test_msg(self):
        """
        message is logged with original field
        """
        r = sync_perform(self.disp, msg("yo!"))
        self.assertIsNone(r)
        self.log.msg.assert_called_once_with("yo!", f1='v')

    def test_msg_with_params(self):
        """
        message is logged with its fields combined
        """
        r = sync_perform(self.disp, msg("yo!", a='b'))
        self.assertIsNone(r)
        self.log.msg.assert_called_once_with("yo!", f1='v', a='b')

    def test_nested_msg(self):
        """
        message is logged when nested inside other effects
        """
        eff = Effect(Constant("foo")).on(
                lambda _: msg("yo", a='b')).on(
                    lambda _: Effect(Constant("goo")))
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.msg.assert_called_once_with("yo", f1='v', a='b')

    def test_multiple_msg(self):
        """
        Multiple messages are logged when there are multiple log effects
        """
        eff = msg("yo", a='b').on(lambda _: msg("goo", d='c'))
        self.assertIsNone(sync_perform(self.disp, eff))
        self.log.msg.assert_has_calls([
            mock.call("yo", f1='v', a='b'),
            mock.call("goo", f1='v', d='c')])

    def test_err(self):
        """
        error is logged with original field
        """
        f = object()
        r = sync_perform(self.disp, err(f, "yo!"))
        self.assertIsNone(r)
        self.log.err.assert_called_once_with(f, "yo!", f1='v')

    def test_err_from_context(self):
        """
        When None is passed as the failure, the exception comes from the
        context at the time of creating the intent, not the time at which the
        intent is performed.
        """
        try:
            raise RuntimeError('original')
        except RuntimeError:
            eff = err(None, "why")
        try:
            raise RuntimeError('performing')
        except RuntimeError:
            sync_perform(self.disp, eff)
        self.log.err.assert_called_once_with(
            CheckFailureValue(RuntimeError('original')),
            'why', f1='v')

    def test_err_from_tuple(self):
        """
        exc_info tuple can be passed as failure when constructing LogErr
        in which case failure will be constructed from the tuple
        """
        eff = err((ValueError, ValueError("a"), None), "why")
        sync_perform(self.disp, eff)
        self.log.err.assert_called_once_with(
            CheckFailureValue(ValueError('a')), 'why', f1='v')

    def test_err_with_params(self):
        """
        error is logged with its fields combined
        """
        f = object()
        r = sync_perform(self.disp, err(f, "yo!", a='b'))
        self.assertIsNone(r)
        self.log.err.assert_called_once_with(f, "yo!", f1='v', a='b')

    def test_nested_err(self):
        """
        error is logged when nested inside other effects
        """
        f = object()
        eff = Effect(Constant("foo")).on(
                lambda _: err(f, "yo", a='b')).on(
                    lambda _: Effect(Constant("goo")))
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.err.assert_called_once_with(f, "yo", f1='v', a='b')

    def test_multiple_err(self):
        """
        Multiple errors are logged when there are multiple LogErr effects
        """
        f1, f2 = object(), object()
        eff = err(f1, "yo", a='b').on(lambda _: err(f2, "goo", d='c'))
        self.assertIsNone(sync_perform(self.disp, eff))
        self.log.err.assert_has_calls([
            mock.call(f1, "yo", f1='v', a='b'),
            mock.call(f2, "goo", f1='v', d='c')])

    def test_boundfields(self):
        """
        When an effect is wrapped `BoundFields` then any logging effect
        inside is performed with fields setup in `BoundFields`
        """
        f = object()
        eff = Effect(Constant("foo")).on(
                lambda _: err(f, "yo", a='b')).on(
                    lambda _: msg("foo", m='d')).on(
                        lambda _: Effect(Constant("goo")))
        eff = with_log(eff, bf='new')
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.msg.assert_called_once_with("foo", f1='v', bf='new', m='d')
        self.log.err.assert_called_once_with(f, "yo", f1='v', bf='new', a='b')

    def test_nested_boundfields(self):
        """
        BoundFields effects can be nested and the log effects internally
        will expand with all bound fields
        """
        eff = Effect(Constant("foo")).on(
                lambda _: msg("foo", m='d')).on(
                    lambda _: Effect(Constant("goo")))
        e = Effect(Constant("abc")).on(lambda _: with_log(eff, i='a')).on(
                lambda _: Effect(Constant("def")))
        self.assertEqual(sync_perform(self.disp, with_log(e, o='f')), "def")
        self.log.msg.assert_called_once_with(
            'foo', i='a', f1='v', m='d', o='f')

    def test_get_fields(self):
        """GetFields results in the fields bound in the effectful context."""
        eff = with_log(get_fields(), ab=12, cd='foo')
        fields = sync_perform(self.disp, eff)
        self.assertEqual(fields, {'f1': 'v', 'ab': 12, 'cd': 'foo'})

    def test_merge_effectful_fields_no_context(self):
        """
        The given log is returned unmodified when there's no effectful context.
        """
        log = mock_log()
        result = merge_effectful_fields(base_dispatcher, log)
        self.assertIs(result, log)

    def test_merge_effectful_fields_no_log_no_context(self):
        """
        The default otter log is returned when no log is passed and there is no
        effectful context.
        """
        result = merge_effectful_fields(base_dispatcher, None)
        self.assertIs(result, default_log)

    def test_merge_effectful_fields_no_log_with_context(self):
        """
        A log is returned with fields from the default otter log and the
        context when no log is passed.
        """
        result = merge_effectful_fields(self.disp, None)
        self.assertEqual(result, matches(IsBoundWith(f1='v', system='otter')))

    def test_merge_effectful_fields_log_and_context(self):
        """
        A log is returned with fields from both the passed-in log and the
        effectful context, with the latter taking precedence.
        """
        log = self.log.bind(f1='v2', passed_log=True)
        result = merge_effectful_fields(self.disp, log)
        self.assertEqual(result, matches(IsBoundWith(passed_log=True, f1='v')))


class MsgWithTimeTests(SynchronousTestCase):
    """
    Tests for :obj:`MsgWithTime`
    """

    def setUp(self):
        self.clock = Clock()
        self.log = mock_log()
        self.disp = ComposedDispatcher([
            get_msg_time_dispatcher(self.clock),
            get_log_dispatcher(self.log, {})
        ])

    def test_logs_msg(self):
        """
        Logs msg with time and returns result of internal effect
        """
        seq = [("internal", lambda i: self.clock.advance(3) or "result")]
        self.assertEqual(
            perform_sequence(
                seq, msg_with_time("mt", Effect("internal")), self.disp),
            "result")
        self.log.msg.assert_called_once_with("mt", seconds_taken=3.0)

    def test_ignores_errors(self):
        """
        Errors are not logged and are propogated
        """
        seq = [("internal", lambda i: raise_(ValueError("oops")))]
        self.assertRaises(
            ValueError, perform_sequence, seq,
            msg_with_time("mt", Effect("internal")), self.disp)
        self.assertFalse(self.log.msg.called)
