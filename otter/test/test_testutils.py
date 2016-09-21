"""
Tests for :obj:`otter.test.utils`.
"""
from effect import (
    ComposedDispatcher, Effect, base_dispatcher, raise_, sync_performer)
from effect.testing import perform_sequence

from mock import ANY

from pyrsistent import pvector

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import Attribute, Interface

from otter.test.utils import (
    iMock,
    retry_sequence
)
from otter.util.retry import (
    Retry,
    ShouldDelayAndRetry,
    repeating_interval,
    retry_times
)


class _ITest1(Interface):
    """I am a interface to be used for testing."""

    first_attribute = Attribute("One attribute")

    def method1(arg1_1, arg1_2, kwarg1_1=None, *args, **kwargs):
        """method"""


class _ITest2(Interface):
    """I am a interface to be used for testing."""

    second_attribute = Attribute("One attribute")

    def method2(arg2_1, arg2_2, kwarg2_1=None):
        """method"""


class _ITest3(Interface):
    """I am a interface to be used for testing."""

    spec = Attribute("Funnily-named attribute")


class IMockTests(SynchronousTestCase):
    """
    Tests for iMock, to ensure it produces a verified (signature-wise, and
    only 1 level deep) fake.
    """
    def test_imock_does_not_include_interface_methods_or_attributes(self):
        """
        Mocking an interface produces only the attributes on the interface
        provided, not attributes on other interfaces and not
        :class:`Interface`-specific attributes and methods such as
        :obj:`Interface.providedBy`.
        """
        im = iMock(_ITest1)
        self.assertTrue(callable(im.method1))
        self.assertFalse(callable(im.first_attribute))

        with self.assertRaises(AttributeError):
            im.providedBy(im)

        with self.assertRaises(AttributeError):
            im.second_attribute

    def test_imock_provides_all_the_interfaces_passed_to_it(self):
        """
        All the attributes on all the interfaces passed to iMock are specced,
        and the resultant mock provides the interfaces.
        """
        im = iMock(_ITest1, _ITest2)
        self.assertTrue(_ITest1.providedBy(im))
        self.assertTrue(_ITest2.providedBy(im))
        self.assertTrue(callable(im.method1))
        self.assertTrue(callable(im.method2))
        self.assertFalse(callable(im.first_attribute))
        self.assertFalse(callable(im.second_attribute))

    def test_imock_methods_have_right_signature(self):
        """
        Passing the wrong number of arguments to methods will raise exceptions.
        """
        im = iMock(_ITest1, _ITest2)
        self.assertRaises(TypeError, im.method1)
        self.assertRaises(TypeError, 'arg1', callableObj=im.method1)
        self.assertRaises(TypeError, 'arg1', 'arg2', 'arg3', 'arg4',
                          callableObj=im.method2)
        self.assertRaises(TypeError, callableObj=im.method2, arg2_1='good',
                          arg2_2='good', nonexistant='bad')
        im.method1('arg1', 'arg2', 'kwarg1', 'any', 'any', any='any')
        im.method2('arg1', 'arg2')
        im.method2(arg2_1='arg1', arg2_2='arg2', kwarg2_1='arg3')

    def test_attributes_are_assignable(self):
        """
        Attributes can be assigned both after the imock is created, and during
        creation via kwargs.
        """
        im = iMock(_ITest1)
        im.first_attribute = "first"
        self.assertEqual(im.first_attribute, "first")

        im = iMock(_ITest1, first_attribute='whoosit')
        self.assertEqual(im.first_attribute, 'whoosit')

    def test_return_values_are_assignable(self):
        """
        Return values can be assigned both after the imock is created, and
        during creation via kwargs.
        """
        im = iMock(_ITest1)
        im.method1.return_value = 5
        self.assertEqual(im.method1(1, 2), 5)

        im = iMock(_ITest1, **{'method1.return_value': 'whoosit'})
        self.assertEqual(im.method1(1, 2), 'whoosit')

    def test_side_effects_are_assignable(self):
        """
        Side effects can be assigned both after the imock is created, and
        during creation via kwargs, and do not interfere with method signature
        checking.
        """
        im = iMock(_ITest1)
        im.method1.side_effect = lambda *a, **kw: 5
        self.assertEqual(im.method1(1, 2), 5)
        self.assertRaises(TypeError, 1, callableObj=im.method1)

        im = iMock(_ITest1, **{'method1.side_effect': lambda *a, **kw: 'meh'})
        self.assertEqual(im.method1(1, 2), 'meh')
        self.assertRaises(TypeError, 1, callableObj=im.method1)

    def test_spec_arg_is_ignored_or_passed_to_interface_if_in_attributes(self):
        """
        If "spec" is passed, it is either ignored, or if one of the interfaces
        has "spec" as an attribute, the attribute is set.  Either way, it is
        not used for speccing a Mock.
        """
        spec = ['one', 'two', 'three']

        for args in ([], [_ITest1], [_ITest3]):
            im = iMock(*args, spec=spec)
            with self.assertRaises(AttributeError):
                im.one

        im = iMock(_ITest3, spec=spec)
        self.assertEqual(im.spec, pvector(spec))

    def test_extra_attributes_and_config_passed_to_mock(self):
        """
        Any attributes and return values provided to iMock that are not
        specified by the interface are passed directly to :class:`MagicMock`.
        They can be ignored (for example if they are method return values for
        methods not in the original spec) or set on the imock (if they are
        just attributes)
        """
        with self.assertRaises(AttributeError):  # because method2 not in
            im = iMock(_ITest1, **{'method2.return_value': 'whoosit'})

        im = iMock(_ITest1, another_attribute='what')
        self.assertEqual(im.another_attribute, 'what')


class RetrySequenceTests(SynchronousTestCase):
    """Tests for :func:`retry_sequence`."""

    def test_retry_sequence_retries_without_delays(self):
        """
        Perform the wrapped effect with the performers given,
        without any delay even if the original intent had a delay.
        """
        r = Retry(
            effect=Effect(1),
            should_retry=ShouldDelayAndRetry(
                can_retry=retry_times(5),
                next_interval=repeating_interval(10)))
        seq = [
            retry_sequence(r, [lambda _: raise_(Exception()),
                               lambda _: raise_(Exception()),
                               lambda _: "yay done"])
        ]
        self.assertEqual(perform_sequence(seq, Effect(r)), "yay done")

    def test_retry_sequence_fails_if_mismatch_sequence(self):
        """
        Fail if the wrong number of performers are given.
        """
        r = Retry(
            effect=Effect(1),
            should_retry=ShouldDelayAndRetry(
                can_retry=retry_times(5),
                next_interval=repeating_interval(10)))
        seq = [
            retry_sequence(r, [lambda _: raise_(Exception()),
                               lambda _: raise_(Exception())])
        ]
        self.assertRaises(AssertionError,
                          perform_sequence, seq, Effect(r))

    def test_do_not_have_to_expect_an_exact_can_retry(self):
        """
        The expected retry intent does not actually have to specify the
        exact ``can_retry`` function, since it might just be a lambda,
        which is hard to compare or hash.
        """
        expected = Retry(effect=Effect(1), should_retry=ANY)
        actual = Retry(effect=Effect(1), should_retry=ShouldDelayAndRetry(
            can_retry=lambda _: False,
            next_interval=repeating_interval(10)))

        seq = [
            retry_sequence(expected, [lambda _: raise_(Exception())])
        ]
        self.assertRaises(Exception,
                          perform_sequence, seq, Effect(actual))

    def test_can_have_a_different_should_retry_function(self):
        """
        The ``should_retry`` function does not have to be a
        :obj:`ShouldDelayAndRetry`.
        """
        expected = Retry(effect=Effect(1), should_retry=ANY)
        actual = Retry(effect=Effect(1), should_retry=lambda _: False)

        seq = [
            retry_sequence(expected, [lambda _: raise_(Exception())])
        ]
        self.assertRaises(Exception,
                          perform_sequence, seq, Effect(actual))

    def test_fallback(self):
        """
        Accept a ``fallback`` dispatcher that will be used if a performer
        returns an effect for an intent that is not covered by the base
        dispatcher.
        """
        def dispatch_2(intent):
            if intent == 2:
                return sync_performer(lambda d, i: "yay done")

        r = Retry(
            effect=Effect(1),
            should_retry=ShouldDelayAndRetry(
                can_retry=retry_times(5),
                next_interval=repeating_interval(10)))

        seq = [
            retry_sequence(r, [lambda _: Effect(2)],
                           fallback_dispatcher=ComposedDispatcher(
                               [dispatch_2, base_dispatcher]))
        ]
        self.assertEqual(perform_sequence(seq, Effect(r)), "yay done")
