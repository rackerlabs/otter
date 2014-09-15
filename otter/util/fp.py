# coding: utf-8

"""Functional programming utilities."""


from pyrsistent import pvector, pmap


"""Functional programming helpers."""


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


def freeze(o):
    """
    Recursively convert a simple Python data structure (lists, tuples,
    dictionaries) into pyrsistent versions of those data structures.
    """
    typ = type(o)
    if typ is dict:
        return pmap({k: freeze(v) for k, v in o.iteritems()})
    elif typ is list:
        return pvector(map(freeze, o))
    elif typ is tuple:
        return tuple(map(freeze, o))
    else:
        return o


def unfreeze(o):
    """
    Recursively convert pyrsistent data structures into basic Python types.
    """
    typ = type(o)
    if typ is type(pvector()):
        return map(unfreeze, o)
    if typ is type(pmap()):
        return {k: unfreeze(v) for k, v in o.iteritems()}
    if typ is tuple:
        return tuple(map(unfreeze, o))
    else:
        return o
