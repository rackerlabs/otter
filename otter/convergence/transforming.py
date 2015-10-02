"""
Functions for transforming collections of steps.

- optimizing (converting multiple steps into one for the purposes of reducing
  API roundtrips)
- limiting (by truncating the number of steps we take)
"""

from functools import partial

from pyrsistent import pbag, pmap, pset

from toolz.curried import groupby
from toolz.itertoolz import concat, concatv

from otter.convergence.steps import (
    AddNodesToCLB,
    CreateServer,
    CreateStack,
    RemoveNodesFromCLB)


_optimizers = {}


def _optimizer(step_type):
    """
    A decorator for a type-specific optimizer.

    Usage::

        @_optimizer(StepTypeToOptimize)
        def optimizing_function(steps_of_that_type):
           return iterable_of_optimized_steps
    """
    def _add_to_optimizers(optimizer):
        _optimizers[step_type] = optimizer
        return optimizer
    return _add_to_optimizers


def _register_bulk_clb_optimizer(step_class, attr_name):
    """
    Merge together multiple CLB bulk steps per load balancer.  This function
    is for generating and registering the :obj:`AddNodesToCLB` and
    :obj:`RemoveNodesFromCLB` optimizers.

    :param step_class: One of :obj:`AddNodesToCLB` or :obj:`RemoveNodesFromCLB`
    :param attr_name: The attribute name on the class that is the iterable that
        needs to be concatenated together to make an optimized step.

    :return: Nothing, because this just registers the optimizers with the
        module.
    """
    def optimize_steps(clb_steps):
        steps_by_lb = groupby(lambda s: s.lb_id, clb_steps)
        return [
            step_class(**{
                'lb_id': lb_id,
                attr_name: pset(concat(getattr(s, attr_name) for s in steps))})
            for lb_id, steps in steps_by_lb.iteritems()
        ]

    _optimizer(step_class)(optimize_steps)

_register_bulk_clb_optimizer(AddNodesToCLB, 'address_configs')
_register_bulk_clb_optimizer(RemoveNodesFromCLB, 'node_ids')


def optimize_steps(steps):
    """
    Optimize steps.

    Currently only optimizes per step type. See the :func:`_optimizer`
    decorator for more information on how to register an optimizer.

    :param pbag steps: Collection of steps.
    :return: a pbag of steps.
    """
    def grouping_fn(step):
        step_type = type(step)
        if step_type in _optimizers:
            return step_type
        else:
            return "unoptimizable"

    steps_by_type = groupby(grouping_fn, steps)
    unoptimizable = steps_by_type.pop("unoptimizable", [])
    omg_optimized = concat(_optimizers[step_type](steps)
                           for step_type, steps in steps_by_type.iteritems())
    return pbag(concatv(omg_optimized, unoptimizable))


_DEFAULT_STEP_LIMITS = pmap({
    CreateServer: 10,
    CreateStack: 10
})


def _limit_step_count(steps, step_limits):
    """
    Limits step count by type.

    :param steps: An iterable of steps.
    :param step_limits: A dict mapping step classes to their maximum allowable
        count. Classes not present in this dict have no limit.
    :return: The input steps
    :rtype: pset
    """
    return pbag(concat(typed_steps[:step_limits.get(cls)]
                       for (cls, typed_steps)
                       in groupby(type, steps).iteritems()))


limit_steps_by_count = partial(
    _limit_step_count, step_limits=_DEFAULT_STEP_LIMITS)
