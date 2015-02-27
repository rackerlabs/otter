# coding: utf-8

"""Functional programming utilities."""

from copy import deepcopy

from characteristic import attributes

from effect import Effect, TypeDispatcher, sync_performer

from toolz.itertoolz import groupby


def wrap(f, g):
    u"""
    'The wrapper combinator'

    Given f, any function, and g, a function which accepts a callable as its
    first argument, return a function:

        λ(*args, **kwargs): g(f, *args, **kwargs)

    This allows g to "wrap" f, so that g is responsible for calling f. g must expect a
    callable as its first argument, of course.

    This is basically a way to do dependency injection -- if a function g
    wants to call f, instead of just referring to f directly, it can accept
    it as a parameter.
    """
    return lambda *args, **kwargs: g(f, *args, **kwargs)


def wrappers(*stuff):
    """
    Combine a number of functions with the wrapper combinator.

    The first function is the 'innermost', and the last is the outermost.
    All functions after the first should take a callable as their first argument.
    """
    return reduce(wrap, stuff)


def partition_groups(grouper, seq, keys):
    """
    Partition a sequence based on a grouping function. This is like groupby,
    but it returns a tuple of fixed length instead of a dict of arbitrary
    length.

    :param callable grouper: A function which returns a key for an item.
    :param seq: A sequence of items.
    :param keys: A sequence of key names to expect.
    :return: A tuple of lists for which the grouper returned each key, in the
        same order as this keys argument.
    """
    groups = groupby(grouper, seq)
    return tuple(groups.get(key, []) for key in keys)


def partition_bool(pred, seq):
    """
    Partition a sequence based on a predicate.

    :param callable pred: Function that will be passed items from seq and
        must return a bool.
    :param seq: sequence of items.
    :returns: 2-tuple of lists, first the elements for which the predicate is
        True, second the elements for which the predicate is False.
    """
    return partition_groups(pred, seq, (True, False))


def predicate_all(*preds):
    """
    Return a predicate function that combines all the given predicate functions
    with and operator
    """
    return lambda *a, **kw: all(p(*a, **kw) for p in preds)


def predicate_any(*preds):
    """
    Return a predicate function that combines all the given predicate functions
    with or operator
    """
    return lambda *a, **kw: any(p(*a, **kw) for p in preds)


def assoc_obj(o, **k):
    """Update attributes on an object, returning a new one."""
    new_o = deepcopy(o)
    new_o.__dict__.update(k)
    return new_o


class ERef(object):
    """
    An effectful mutable variable.

    Compare to Haskell's ``IORef`` or Clojure's ``atom``.
    """

    def __init__(self, initial):
        self._value = initial

    def read(self):
        """Return an Effect that results in the current value."""
        return Effect(ReadERef(eref=self))

    def modify(self, transformer):
        """
        Return an Effect that updates the value with ``fn(old_value)``.

        This is not thread-safe.
        """
        return Effect(ModifyERef(eref=self, transformer=transformer))


@attributes(['eref'])
class ReadERef(object):
    """Intent that gets an ERef value."""


@attributes(['eref', 'transformer'])
class ModifyERef(object):
    """Intent that modifies an ERef value in-place with a transformer func."""


@sync_performer
def perform_read_eref(dispatcher, intent):
    return intent.eref._value


@sync_performer
def perform_modify_eref(dispatcher, intent):
    new_value = intent.transformer(intent.eref._value)
    intent.eref._value = new_value
    return new_value


eref_dispatcher = TypeDispatcher({ReadERef: perform_read_eref,
                                  ModifyERef: perform_modify_eref})
