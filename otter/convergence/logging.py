"""Utilities for formatting log messages."""

from collections import defaultdict
from functools import partial

from effect import parallel

from pyrsistent import thaw

from toolz.curried import groupby
from toolz.itertoolz import concat

from otter.convergence.steps import (
    AddNodesToCLB, BulkAddToRCv3, BulkRemoveFromRCv3, ChangeCLBNode,
    CreateServer, DeleteServer, RemoveNodesFromCLB, SetMetadataItemOnServer)
from otter.log.cloudfeeds import cf_msg


# - it kinda sucks that we're using separate effects for all of
# these, maybe? CF has an API for sending a bunch of events at once and it'd be
# good to use it. OTOH it could also be implemented at the logging observer
# layer by using a "nagle".


_loggers = {}


def _logger(step_type):
    """Declare a function for logging a bag of steps of a particular type."""
    def _add_to_loggers(f):
        _loggers[step_type] = f
    return _add_to_loggers


@_logger(CreateServer)
def _(steps):
    by_cfg = groupby(lambda s: s.server_config, steps)
    effs = [
        cf_msg(
            'convergence-create-servers',
            num_servers=len(cfg_steps),
            server_config=dict(cfg))
        # We sort the items with `thaw` because PMap does not support
        # comparison
        for cfg, cfg_steps in sorted(by_cfg.iteritems(), key=thaw)]
    return parallel(effs)


@_logger(SetMetadataItemOnServer)
def _log_set_metadata(steps):
    by_kv = groupby(lambda s: (s.key, s.value), steps)
    effs = [
        cf_msg(
            'convergence-set-server-metadata',
            servers=sorted(s.server_id for s in kvsteps),
            key=key, value=value
        )
        for (key, value), kvsteps in sorted(by_kv.iteritems())
    ]
    return parallel(effs)


@_logger(DeleteServer)
def _log_delete_servers(steps):
    return cf_msg(
        'convergence-delete-servers',
        servers=sorted([s.server_id for s in steps]))


@_logger(AddNodesToCLB)
def _log_add_nodes_clb(steps):
    lbs = defaultdict(list)
    for step in steps:
        for (address, config) in step.address_configs:
            lbs[step.lb_id].append('%s:%s' % (address, config.port))
    effs = [
        cf_msg('convergence-add-clb-nodes',
               lb_id=lb_id, addresses=sorted(addresses))
        for lb_id, addresses in sorted(lbs.iteritems())
    ]
    return parallel(effs)


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
               nodes=sorted([s.node_id for s in grouped_steps]),
               condition=condition.name, weight=weight, type=node_type.name)
        for (lb, condition, weight, node_type), grouped_steps
        in sorted(lbs.iteritems())
    ]
    return parallel(effs)


def _log_bulk_rcv3(event, steps):
    by_lbs = groupby(lambda s: s[0], concat(s.lb_node_pairs for s in steps))
    effs = [
        cf_msg(event,
               lb_id=lb_id,
               servers=sorted(p[1] for p in pairs))
        for lb_id, pairs in sorted(by_lbs.iteritems())
    ]
    return parallel(effs)


_logger(BulkAddToRCv3)(
    partial(_log_bulk_rcv3, 'convergence-add-rcv3-nodes'))
_logger(BulkRemoveFromRCv3)(
    partial(_log_bulk_rcv3, 'convergence-remove-rcv3-nodes'))


def log_steps(steps):
    """
    Log some steps (to cloud feeds).

    In general this tries to reduce the number of Log calls to a reasonable
    minimum, based on how steps are usually used. For example, multiple
    :obj:`SetMetadataItemOnServer` that are setting the same key/value on a
    server will be merged into one Log call that shows all the servers being
    affected.
    """
    steps_by_type = groupby(type, steps)
    effs = []
    for step_type, typed_steps in steps_by_type.iteritems():
        if step_type in _loggers:
            effs.append(_loggers[step_type](typed_steps))
    return parallel(effs)
