# coding: utf-8

"""Functional programming utilities."""

from copy import deepcopy

from pyrsistent import PMap, freeze, thaw

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


def set_in(old_dict, keys, new_value):
    """
    Take the old dictionary and traverses the dictionary via the list of
    keys.  The returned dictionary will be the same as the old dictionary,
    but with the resultant value set as ``new_value``.

    Note that if more than 1 key is passed, and any of the keys (except for the
    last) do not already exist, raises KeyError or IndexError.

    Note that the new value does not need to be a pyrsistent data structure -
    this function will freeze everything first.

    :param dict old_dict: The dictionary to change values for.
    :param iterable keys: An ordered collection of keys
    :param new_value: The value to set the keys to

    :return: A copy of the old dictionary as PMap, with the new value.
    """
    if len(keys) < 1:
        raise ValueError("Must provide one or more keys")

    if isinstance(old_dict, PMap):
        new_mutable = thaw(old_dict)
    else:
        new_mutable = deepcopy(old_dict)

    to_change = new_mutable
    for k in keys[:-1]:
        # If there is no mapping, or the value isn't a dict, make the
        # valeu be a dictionary
        if not isinstance(to_change.get(k), dict):
            to_change[k] = {}
        to_change = to_change[k]

    to_change[keys[-1]] = new_value

    return freeze(new_mutable)
