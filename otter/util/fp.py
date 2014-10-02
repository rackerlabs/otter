# coding: utf-8

"""Functional programming utilities."""


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
    return lambda a: reduce(lambda p1, p2: p1(a) and p2(a), preds)
