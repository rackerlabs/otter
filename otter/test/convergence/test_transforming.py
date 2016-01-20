"""Tests for otter.convergence.transforming."""

from pyrsistent import pbag, pmap, pset, s

from toolz import groupby

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.model import CLBDescription
from otter.convergence.steps import (
    AddNodesToCLB,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    CreateServer,
    CreateStack,
    DeleteServer,
    RemoveNodesFromCLB,
    )
from otter.convergence.transforming import (
    _limit_step_count,
    limit_steps_by_count,
    optimize_steps)
from otter.test.utils import set_config_for_test


class LimitStepCount(SynchronousTestCase):
    """
    Tests for limiting step counts.
    """

    def _create_some_steps(self, counts={}):
        """
        Creates some steps for testing.

        :param counts: A mapping of supported step classes to the number of
            those steps to create. If unspecified, assumed to be zero.
        :return: A pbag of steps.
        """
        create_servers = [CreateServer(server_config=pmap({"sentinel": i}))
                          for i in xrange(counts.get(CreateServer, 0))]
        delete_servers = [DeleteServer(server_id='abc-' + str(i))
                          for i in xrange(counts.get(DeleteServer, 0))]
        remove_from_clbs = [RemoveNodesFromCLB(lb_id='1', node_ids=(str(i),))
                            for i in xrange(counts.get(RemoveNodesFromCLB, 0))]

        return pbag(create_servers + delete_servers + remove_from_clbs)

    def _test_limit_step_count(self, in_step_counts, step_limits):
        """
        Create some steps, limit them, assert they were limited.
        """
        in_steps = self._create_some_steps(in_step_counts)
        out_steps = _limit_step_count(in_steps, step_limits)
        expected_step_counts = {
            cls: step_limits.get(cls, in_step_count)
            for (cls, in_step_count)
            in in_step_counts.iteritems()
        }
        actual_step_counts = {
            cls: len(steps_of_this_type)
            for (cls, steps_of_this_type)
            in groupby(type, out_steps).iteritems()
        }
        self.assertEqual(expected_step_counts, actual_step_counts)

    def test_limit_step_count(self):
        """
        The steps are limited so that there are at most as many of each
        type as specified,. If no limit is specified for a type, any
        number of them are allowed.
        """
        in_step_counts = {
            CreateServer: 10,
            DeleteServer: 10
        }
        step_limits = {
            CreateServer: 3,
            DeleteServer: 10
        }
        self._test_limit_step_count(in_step_counts, step_limits)

    def test_default_step_limit(self):
        """
        The default limit limits server creation to up to 10 steps.
        """
        limits = limit_steps_by_count.keywords["step_limits"]
        self.assertEqual(limits, pmap({CreateServer: 10, CreateStack: 10}))

    def test_default_step_limit_config(self):
        """
        The default limit limits server creation to up to 10 steps.
        """
        set_config_for_test(
            self, {"converger": {"create_server_steps_limit": 100}})
        from otter.convergence import transforming as t
        reload(t)
        limits = t.limit_steps_by_count.keywords["step_limits"]
        self.assertEqual(limits, pmap({CreateServer: 100, CreateStack: 10}))


class OptimizerTests(SynchronousTestCase):
    """Tests for :func:`optimize_steps`."""

    def test_optimize_clb_adds(self):
        """
        Multiple :class:`AddNodesToCLB` steps for the same LB
        are merged into one.
        """
        steps = pbag([
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.2.3.4',
                                   CLBDescription(lb_id='5', port=80))))])
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToCLB(
                    lb_id='5',
                    address_configs=s(
                        ('1.1.1.1', CLBDescription(lb_id='5', port=80)),
                        ('1.2.3.4', CLBDescription(lb_id='5', port=80)))
                )]))

    def test_optimize_clb_adds_maintain_unique_ports(self):
        """
        Multiple ports can be specified for the same address and LB ID when
        adding to a CLB.
        """
        steps = pbag([
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=8080))))])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToCLB(
                    lb_id='5',
                    address_configs=s(
                        ('1.1.1.1',
                         CLBDescription(lb_id='5', port=80)),
                        ('1.1.1.1',
                         CLBDescription(lb_id='5', port=8080))))]))

    def test_clb_adds_multiple_load_balancers(self):
        """
        Aggregation is done on a per-load-balancer basis when adding to a CLB.
        """
        steps = pbag([
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.2',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='6', port=80)))),
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('1.1.1.2',
                                   CLBDescription(lb_id='6', port=80)))),
        ])
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToCLB(
                    lb_id='5',
                    address_configs=s(
                        ('1.1.1.1', CLBDescription(lb_id='5', port=80)),
                        ('1.1.1.2', CLBDescription(lb_id='5', port=80)))),
                AddNodesToCLB(
                    lb_id='6',
                    address_configs=s(
                        ('1.1.1.1', CLBDescription(lb_id='6', port=80)),
                        ('1.1.1.2', CLBDescription(lb_id='6', port=80)))),
            ]))

    def test_optimize_clb_removes(self):
        """
        Aggregation is done on a per-load-balancer basis when remove nodes from
        a CLB.
        """
        steps = pbag([
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('2')),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('3')),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('4'))])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                RemoveNodesFromCLB(lb_id='5', node_ids=s('1', '2', '3', '4'))
            ]))

    def test_clb_remove_multiple_load_balancers(self):
        """
        Multiple :class:`RemoveNodesFromCLB` steps for the same LB
        are merged into one.
        """
        steps = pbag([
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('2')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('3')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('4'))])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                RemoveNodesFromCLB(lb_id='5', node_ids=s('1', '2')),
                RemoveNodesFromCLB(lb_id='6', node_ids=s('3', '4'))
            ]))

    def test_optimize_leaves_other_steps(self):
        """
        Unoptimizable steps pass the optimizer unchanged.
        """
        steps = pbag([
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            CreateServer(server_config=pmap({})),
            BulkRemoveFromRCv3(lb_node_pairs=pset([("lb-1", "node-a")])),
            BulkAddToRCv3(lb_node_pairs=pset([("lb-2", "node-b")]))
            # Note that the add & remove pair should not be the same;
            # the optimizer might reasonably optimize opposite
            # operations away in the future.
        ])
        self.assertEqual(
            optimize_steps(steps),
            steps)

    def test_mixed_optimization(self):
        """
        Mixes of optimizable and unoptimizable steps still get optimized
        correctly.
        """
        steps = pbag([
            # CLB adds
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.2',
                                   CLBDescription(lb_id='5', port=80)))),
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='6', port=80)))),
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('1.1.1.2',
                                   CLBDescription(lb_id='6', port=80)))),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('2')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('3')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('4')),

            # Unoptimizable steps
            CreateServer(server_config=pmap({})),
        ])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                # Optimized CLB adds
                AddNodesToCLB(
                    lb_id='5',
                    address_configs=s(('1.1.1.1',
                                       CLBDescription(lb_id='5', port=80)),
                                      ('1.1.1.2',
                                       CLBDescription(lb_id='5', port=80)))),
                AddNodesToCLB(
                    lb_id='6',
                    address_configs=s(('1.1.1.1',
                                       CLBDescription(lb_id='6', port=80)),
                                      ('1.1.1.2',
                                       CLBDescription(lb_id='6', port=80)))),
                RemoveNodesFromCLB(lb_id='5', node_ids=s('1', '2')),
                RemoveNodesFromCLB(lb_id='6', node_ids=s('3', '4')),

                # Unoptimizable steps
                CreateServer(server_config=pmap({}))
            ]))
