"""Utilities for formatting log messages."""

from collections import defaultdict

from effect import parallel

from pyrsistent import thaw

from toolz.curried import groupby
from toolz.itertoolz import concat

from otter.convergence.steps import (
    AddNodesToCLB, BulkAddToRCv3, ChangeCLBNode, CreateServer, DeleteServer,
    RemoveNodesFromCLB)
from otter.log.cloudfeeds import cf_msg


# Comments: - it kinda sucks that we're using separate effects for all of
# these, maybe? CF has an API for sending a bunch of events at once and it'd be
# good to use it. OTOH it could also be implemented at the logging observer
# layer by using a "nagle".


_loggers = {}


def _logger(step_type):
    def _add_to_loggers(f):
        _loggers[step_type] = f
    return _add_to_loggers


@_logger(CreateServer)
def _(steps):
    # XXX RADIX TODO: groupby the server_config so we don't assume they're all
    # the same.
    return cf_msg(
        'convergence-create-servers',
        num_servers=len(steps),
        server_config=thaw(next(iter(steps)).server_config),
    )


# Intentionally leaving out SetMetadataItemOnServer for now, since it seems
# kind of low-level

@_logger(DeleteServer)
def _log_delete_servers(steps):
    return cf_msg(
        'convergence-delete-servers',
        server_ids=sorted([s.server_id for s in steps]))


@_logger(AddNodesToCLB)
def _log_add_nodes_clb(steps):
    lbs = defaultdict(list)
    for step in steps:
        for (address, config) in step.address_configs:
            lbs[step.lb_id].append('%s:%s' % (address, config.port))

    def msg(lb_id, addresses):
        formatted_addresses = ', '.join(sorted(addresses))
        return cf_msg('convergence-add-clb-nodes',
                      lb_id=lb_id, addresses=formatted_addresses)

    return parallel([msg(lb_id, addresses)
                     for lb_id, addresses in sorted(lbs.iteritems())])


@_logger(RemoveNodesFromCLB)
def _log_remove_from_clb(steps):
    lbs = groupby(lambda s: s.lb_id, steps)
    effs = [
        cf_msg('convergence-remove-clb-nodes',
               lb_id=lb, nodes=sorted(concat(s.node_ids for s in lbsteps)))
        for lb, lbsteps in sorted(lbs.iteritems())]
    return parallel(effs)


@_logger(ChangeCLBNode)
def _log_change_clb_node(steps):
    lbs = groupby(lambda s: (s.lb_id, s.condition, s.weight, s.type),
                  steps)
    effs = [
        cf_msg('convergence-change-clb-nodes',
               lb_id=lb,
               nodes=', '.join(sorted([s.node_id for s in grouped_steps])),
               condition=condition.name, weight=weight, type=node_type.name)
        for (lb, condition, weight, node_type), grouped_steps
        in sorted(lbs.iteritems())
    ]
    return parallel(effs)


@_logger(BulkAddToRCv3)
def _log_bulkadd_rcv3(steps):
    by_lbs = groupby(lambda s: s[0], concat(s.lb_node_pairs for s in steps))
    effs = [
        cf_msg('convergence-add-rcv3-nodes',
               lb_id=lb_id, nodes=', '.join(sorted(p[1] for p in pairs)))
        for lb_id, pairs in sorted(by_lbs.iteritems())
    ]
    return parallel(effs)


def log_steps(steps):
    steps_by_type = groupby(type, steps)
    effs = []
    for step_type, typed_steps in steps_by_type.iteritems():
        if step_type in _loggers:
            effs.append(_loggers[step_type](typed_steps))
    return parallel(effs)
