"""Tests for otter.convergence.transforming."""

from hypothesis import given
import hypothesis.strategies as st

from pyrsistent import pbag, pmap, pset, s

from toolz import groupby

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.model import (
    CLBDescription,
    CLBNodeCondition,
    CLBNodeType)
from otter.convergence.steps import (
    AddNodesToCLB,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    CreateServer,
    CreateStack,
    DeleteServer,
    RemoveNodesFromCLB,
    )
from otter.convergence.transforming import (
    filter_clb_mutating_types,
    get_step_limits_from_conf,
    limit_steps_by_count,
    optimize_steps)
from otter.util.fp import partition_bool


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
        out_steps = limit_steps_by_count(in_steps, step_limits)
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

    def test_get_limits_conf(self):
        """
        `get_step_limits_from_conf` will return configured limit along with
        default limit
        """
        limits = get_step_limits_from_conf({"create_server": 100})
        self.assertEqual(limits, {CreateServer: 100, CreateStack: 10})


class FilterMutatingCLBTests(SynchronousTestCase):
    """
    Tests for :func:`filter_clb_mutating_types`
    """

    sample_steps = [
        CreateServer(server_config=pmap({"name": "server"})),
        CreateServer(server_config=pmap({"name": "server2"})),
        DeleteServer(server_id="abc"), DeleteServer(server_id="def"),
        AddNodesToCLB(
            lb_id='5',
            address_configs=s(('1.1.1.1',
                               CLBDescription(lb_id='5', port=80)))),
        AddNodesToCLB(
            lb_id='5',
            address_configs=s(('1.2.3.4',
                               CLBDescription(lb_id='5', port=80)))),
        AddNodesToCLB(
            lb_id='6',
            address_configs=s(('2.1.1.1',
                               CLBDescription(lb_id='6', port=80)))),
        AddNodesToCLB(
            lb_id='6',
            address_configs=s(('2.2.3.4',
                               CLBDescription(lb_id='6', port=80)))),
        RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
        RemoveNodesFromCLB(lb_id='5', node_ids=s('2')),
        RemoveNodesFromCLB(lb_id='6', node_ids=s('3')),
        RemoveNodesFromCLB(lb_id='6', node_ids=s('4')),
        ChangeCLBNode(
            lb_id='5',
            node_id='1',
            condition=CLBNodeCondition.DRAINING,
            weight=50,
            type=CLBNodeType.PRIMARY),
        ChangeCLBNode(
            lb_id='5',
            node_id='2',
            condition=CLBNodeCondition.ENABLED,
            weight=10,
            type=CLBNodeType.PRIMARY),
        ChangeCLBNode(
            lb_id='6',
            node_id='3',
            condition=CLBNodeCondition.DRAINING,
            weight=10,
            type=CLBNodeType.PRIMARY),
        ChangeCLBNode(
            lb_id='6',
            node_id='4',
            condition=CLBNodeCondition.ENABLED,
            weight=15,
            type=CLBNodeType.SECONDARY)
    ]

    @given(st.lists(st.sampled_from(sample_steps)))
    def test_only_one_mutating_type(self, steps):
        """
        Test that after filtering only one CLB mutating type steps exist per
        CLB. Also ensure that non-CLB steps remain intact.
        """
        steps = pbag(steps)

        clb_types = (AddNodesToCLB, RemoveNodesFromCLB, ChangeCLBNode)
        lb_steps, no_lb_steps = partition_bool(lambda s: type(s) in clb_types,
                                               steps)
        steps_by_id = groupby(lambda s: s.lb_id, lb_steps)

        filtered = filter_clb_mutating_types(steps)

        filtered_steps_by_id = groupby(lambda s: getattr(s, "lb_id", "no"),
                                       filtered)
        for lb_id, lb_steps in steps_by_id.items():
            steps_by_type = groupby(type, lb_steps)
            filtered_steps_by_types = groupby(type,
                                              filtered_steps_by_id[lb_id])
            # Ensure only one CLB type per CLB
            self.assertEqual(len(filtered_steps_by_types), 1)
            filtered_lb_type = filtered_steps_by_types.keys()[0]
            # The returned steps of LB type is same as original
            self.assertEqual(
                filtered_steps_by_types[filtered_lb_type],
                steps_by_type[filtered_lb_type])

        # Ensure non-CLB steps remain intact
        self.assertEqual(no_lb_steps, filtered_steps_by_id.get("no", []))


class OptimizerTests(SynchronousTestCase):
    """Tests for :func:`optimize_steps`."""

    def test_filters_clb_types(self):
        """
        Only one CLB type is returned per CLB
        """
        steps = pbag([
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            # Another CLB type for CLB 5. Will be removed
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('2')),
            # Another CLB type for CLB 6. Will be removed
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='6', port=80)))),
            # Unoptimizable steps
            CreateServer(server_config=pmap({})),
        ])
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToCLB(
                    lb_id='5',
                    address_configs=s(
                        ('1.1.1.1', CLBDescription(lb_id='5', port=80)))),
                RemoveNodesFromCLB(lb_id='6', node_ids=s('2')),
                CreateServer(server_config=pmap({}))
            ])
        )

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
            RemoveNodesFromCLB(lb_id='6', node_ids=s('1')),
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
            RemoveNodesFromCLB(lb_id='7', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='7', node_ids=s('2')),

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
                RemoveNodesFromCLB(lb_id='7', node_ids=s('1', '2')),

                # Unoptimizable steps
                CreateServer(server_config=pmap({}))
            ]))

    def _test_rcv3_step(self, step_class):
        steps = [
            step_class(
                lb_node_pairs=pset([("l1", "s1"), ("l1", "s2")])),
            step_class(lb_node_pairs=pset([("l2", "s1")])),
            step_class(lb_node_pairs=pset([("l1", "s3"), ("l2", "s3")]))
        ]
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                step_class(
                    lb_node_pairs=pset([
                        ("l1", "s1"), ("l1", "s2"), ("l2", "s1"), ("l1", "s3"),
                        ("l2", "s3")
                    ])
                )
            ])
        )

    def test_rcv3_add(self):
        """
        Multiple BulkAddToRCv3 steps are combined into one step
        """
        self._test_rcv3_step(BulkAddToRCv3)

    def test_rcv3_remove(self):
        """
        Multiple BulkRemoveFromRCv3 steps are combined into one step
        """
        self._test_rcv3_step(BulkRemoveFromRCv3)

    def test_rcv3_mixed(self):
        """
        Multiple BulkAddToRCv3 and BulkRemoveFromRCv3 steps are combined
        into one BulkAddToRCv3 step and one BulkRemoveFromRCv3 step
        """
        steps = [
            BulkAddToRCv3(
                lb_node_pairs=pset([("l1", "s1"), ("l1", "s2")])),
            # Same pair for different class does not conflict
            BulkRemoveFromRCv3(lb_node_pairs=pset([("l1", "s1")])),
            BulkAddToRCv3(lb_node_pairs=pset([("l1", "s3")])),
            BulkRemoveFromRCv3(
                lb_node_pairs=pset([("l3", "s3"), ("l2", "s3")]))
        ]
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                BulkAddToRCv3(
                    lb_node_pairs=pset([
                        ("l1", "s1"), ("l1", "s2"), ("l1", "s3")])),
                BulkRemoveFromRCv3(
                    lb_node_pairs=pset([
                        ("l1", "s1"), ("l3", "s3"), ("l2", "s3")]))
            ])
        )
