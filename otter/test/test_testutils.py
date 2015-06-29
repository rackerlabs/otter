"""
Tests for :obj:`otter.test.utils`.
"""
from effect import (
    ComposedDispatcher, Effect,
    base_dispatcher, parallel, sync_performer)

from pyrsistent import pvector

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import Attribute, Interface

from otter.test.utils import iMock, nested_parallel, perform_sequence


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


class NestedParallelTests(SynchronousTestCase):
    """Tests for :func:`nested_parallel`."""

    def test_nested_parallel(self):
        """
        Ensures that all parallel effects are found in the given intents, in
        order, and returns the results associated with those intents.
        """
        seq = [
            nested_parallel([
                (1, lambda i: "one!"),
                (2, lambda i: "two!"),
                (3, lambda i: "three!"),
            ])
        ]
        p = parallel([Effect(1), Effect(2), Effect(3)])
        self.assertEqual(perform_sequence(seq, p), ['one!', 'two!', 'three!'])

    def test_fallback(self):
        """
        Accepts a ``fallback`` dispatcher that will be used when the sequence
        doesn't contain an intent.
        """
        def dispatch_2(intent):
            if intent == 2:
                return sync_performer(lambda d, i: "two!")
        fallback = ComposedDispatcher([dispatch_2, base_dispatcher])
        seq = [
            nested_parallel([
                (1, lambda i: 'one!'),
                (3, lambda i: 'three!'),
                ],
                fallback_dispatcher=fallback),
        ]
        p = parallel([Effect(1), Effect(2), Effect(3)])
        self.assertEqual(perform_sequence(seq, p), ['one!', 'two!', 'three!'])
