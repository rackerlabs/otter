"""Tests for otter.convergence.transforming."""

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
    RemoveNodesFromCLB)
from otter.convergence.transforming import (
    get_step_limits_from_conf,
    limit_steps_by_count,
    one_clb_step,
    optimize_steps)


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


class OneCLBStepTests(SynchronousTestCase):
    """
    Tests for :func:`one_clb_step`
    """

    def test_no_clb_steps(self):
        """
        Returns same steps when there are no CLB steps passed
        """
        steps = [
            CreateServer(server_config=pmap({"name": "server"})),
            DeleteServer(server_id="abc")
        ]
        self.assertEqual(list(one_clb_step(steps)), steps)

    def test_mixed(self):
        """
        When there are multiple steps of same CLB then first step of each CLB
        is returned
        """
        steps = [
            CreateServer(server_config=pmap({"name": "server"})),
            DeleteServer(server_id="abc"),
            AddNodesToCLB(
                lb_id='5',
                address_configs=s(('1.1.1.1',
                                   CLBDescription(lb_id='5', port=80)))),
            RemoveNodesFromCLB(lb_id='5', node_ids=s('1')),
            RemoveNodesFromCLB(lb_id='6', node_ids=s('3')),
            AddNodesToCLB(
                lb_id='6',
                address_configs=s(('2.1.1.1',
                                   CLBDescription(lb_id='6', port=80)))),
            ChangeCLBNode(
                lb_id='7',
                node_id='9',
                condition=CLBNodeCondition.ENABLED,
                weight=10,
                type=CLBNodeType.PRIMARY),
            RemoveNodesFromCLB(lb_id='7', node_ids=s('4')),
            AddNodesToCLB(
                lb_id='7',
                address_configs=s(('3.1.1.1',
                                   CLBDescription(lb_id='9', port=80)))),
            ChangeCLBNode(
                lb_id='5',
                node_id='11',
                condition=CLBNodeCondition.ENABLED,
                weight=10,
                type=CLBNodeType.PRIMARY)
        ]
        self.assertEqual(
            list(one_clb_step(steps)),
            (steps[:3] +    # Non-CLB steps and 1 step for CLB 5
             [steps[4]] +   # One step for CLB 6
             [steps[6]])    # One step for CLB 7
        )


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
