"""Utilities for formatting log messages."""

from collections import defaultdict

from effect import parallel

from pyrsistent import thaw

from toolz.curried import groupby
from toolz.itertoolz import concat

from otter.convergence.steps import (
    AddNodesToCLB, CreateServer, DeleteServer, RemoveNodesFromCLB)
from otter.log.cloudfeeds import cf_msg


_loggers = {}

def _logger(step_type):
    def _add_to_loggers(f):
        _loggers[step_type] = f
    return _add_to_loggers


@_logger(CreateServer)
def _(steps):
    # Here we assume that all of the servers have the same server_config.
    # Could also change this to support differing server_configs by producing
    # one log message per config.
    return cf_msg(
        'convergence-create-servers',
        num_servers=len(steps),
        server_config=thaw(next(iter(steps)).server_config),
    )


@_logger(DeleteServer)
def _(steps):
    return cf_msg(
        'convergence-delete-servers',
        server_ids=sorted([s.server_id for s in steps]))

## Intentionally leaving out SetMetadataItemOnServer for now, since it seems
## kind of low-level

@_logger(AddNodesToCLB)
def _(steps):
    lbs = defaultdict(list)
    for step in steps:
        for (address, config) in step.address_configs:
            lbs[step.lb_id].append('%s:%s' % (address, config.port))

    def msg(lb_id, addresses):
        formatted_addresses = ', '.join(sorted(addresses))
        return cf_msg('convergence-add-nodes-to-clb',
                      lb_id=lb_id, addresses=formatted_addresses)

    return parallel([msg(lb_id, addresses)
                     for lb_id, addresses in sorted(lbs.iteritems())])


@_logger(RemoveNodesFromCLB)
def _(steps):
    lbs = groupby(lambda s: s.lb_id, steps)
    effs = [
        cf_msg('convergence-remove-nodes-from-clb',
               lb_id=lb, nodes=sorted(concat(s.node_ids for s in lbsteps)))
        for lb, lbsteps in sorted(lbs.iteritems())]
    return parallel(effs)


def log_steps(steps):
    steps_by_type = groupby(type, steps)
    effs = []
    for step_type, typed_steps in steps_by_type.iteritems():
        if step_type in _loggers:
            effs.append(_loggers[step_type](typed_steps))
    return parallel(effs)
