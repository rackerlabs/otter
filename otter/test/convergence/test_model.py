"""
Tests for convergence models.
"""

from characteristic import attributes

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import implementer

from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    IDrainable,
    ILBDescription,
    ILBNode,
    NovaServer,
    ServerState,
    StepResult
)


@implementer(ILBDescription)
class DummyLBDescription(object):
    """
    Fake LB description to be use for equality testing.
    """
    def equivalent_definition(self, other):
        """Just always return True"""
        return True


@attributes(["servicenet_address"])
class DummyServer(object):
    """
    Fake Server object to be used for tesitng.
    """


class CLBDescriptionTests(SynchronousTestCase):
    """
    Tests for :class:`CLBDescription`.
    """
    def test_provides_ILBDescription(self):
        """
        An instance of :class:`CLBDescription` provides :class:`ILBDescription`.
        """
        desc = CLBDescription(lb_id='12345', port=80)
        self.assertTrue(ILBDescription.providedBy(desc))

    def test_only_eq_and_equivalent_definition_to_other_CLBDescriptions(self):
        """
        :func:`CLBDescriptionTest.__eq__` and
        :func:`CLBDescriptionTest.equivalent_definition` return false if
        compared to a non-:class:`CLBDescription` :class:`ILBDescription`
        provider.
        """
        desc = CLBDescription(lb_id='12345', port=80)
        fake = DummyLBDescription()
        self.assertNotEqual(desc, fake)
        self.assertFalse(desc.equivalent_definition(fake))

    def test_equivalent_definition_but_not_eq(self):
        """
        Even if weight, etc. are different, so long as the ``lb_id`` and ``port``
        are identical, :func:`CLBDescription.equivalent_definition` will
        return `True`.  :func:`CLBDescription.__eq__` will not, however.
        """
        desc1 = CLBDescription(lb_id='12345', port=80)
        desc2 = CLBDescription(lb_id='12345', port=80, weight=2,
                               condition=CLBNodeCondition.DISABLED,
                               type=CLBNodeType.SECONDARY)
        self.assertTrue(desc1.equivalent_definition(desc2))
        self.assertNotEqual(desc1, desc2)

    def test_neither_equivalent_definition_or_eq(self):
        """
        If ``lb_id`` and ``port`` are different, even if everything else are
        the same, neither :func:`CLBDescription.equivalent_definition` nor
        :func:`CLBDescription.__eq__` will return `True`.
        """
        desc1 = CLBDescription(lb_id='12345', port=80)
        desc2 = CLBDescription(lb_id='12345', port=8080)
        self.assertFalse(desc1.equivalent_definition(desc2))
        self.assertNotEqual(desc1, desc2)

    def test_equivalent_definition_and_eq(self):
        """
        If every attribute is the same, both :func:`CLBDescription.__eq__` and
        :func:`CLBDescription.equivalent_definition` will return `True`.
        """
        desc1 = CLBDescription(lb_id='12345', port=80)
        desc2 = CLBDescription(lb_id='12345', port=80)
        self.assertTrue(desc1.equivalent_definition(desc2))
        self.assertEquals(desc1, desc2)


class CLBNodeTests(SynchronousTestCase):
    """
    Tests for :class:`CLBNode`.
    """
    desc = CLBDescription(lb_id='12345', port=80)
    drain_desc = CLBDescription(lb_id='12345', port=80,
                                condition=CLBNodeCondition.DRAINING)

    def test_provides_ILBDescription_and_IDrainable(self):
        """
        An instance of :class:`CLBNode` provides :class:`ILBNode` and
        :class:`IDrainable`.
        """
        node = CLBNode(node_id='1234', description=self.desc, address='10.1.1.1')
        self.assertTrue(ILBNode.providedBy(node))
        self.assertTrue(IDrainable.providedBy(node))

    def test_matches_only_works_with_NovaServers(self):
        """
        :func:`CLBNode.matches` returns false if the server is not an instance
        of :class:`NovaServer`.
        """
        node = CLBNode(node_id='1234', description=self.desc, address='10.1.1.1')
        self.assertFalse(node.matches(DummyServer(servicenet_address="10.1.1.1")))

    def test_matches_only_if_NovaServer_address_matches_node_address(self):
        """
        :func:`CLBNode.matches` returns True only if the :class:`NovaServer` has
        the same ServiceNet address as the node address
        """
        node = CLBNode(node_id='1234', description=self.desc, address='10.1.1.1')
        self.assertFalse(node.matches(
            NovaServer(id='1', state=ServerState.ACTIVE, created=0.0,
                       servicenet_address="10.1.1.2")))
        self.assertTrue(node.matches(
            NovaServer(id='1', state=ServerState.ACTIVE, created=0.0,
                       servicenet_address="10.1.1.1")))

    def test_current_draining_true_if_description_is_draining(self):
        """
        :func:`CLBNode.currently_draining` returns `True` if
        `CLBNode.description.condition` is :obj:`CLBNodeCondition.DRAINING`
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1')
        self.assertTrue(node.currently_draining())

    def test_current_draining_false_if_description_not_draining(self):
        """
        :func:`CLBNode.currently_draining` returns `False` if
        `CLBNode.description.condition` is not :obj:`CLBNodeCondition.DRAINING`
        """
        node = CLBNode(node_id='1234', description=self.desc, address='10.1.1.1')
        self.assertFalse(node.currently_draining())

    def test_done_draining_past_timeout_even_if_there_are_connections(self):
        """
        If there are still connections, but the node has been in draining past
        the timeout, :func:`CLBNode.is_done_draining` returns `True`.
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1', drained_at=0.0, connections=1)
        self.assertTrue(node.is_done_draining(now=30, timeout=15))

    def test_done_draining_past_timeout_even_if_no_connection_info(self):
        """
        If connection information is not provided, and the node has been in
        draining past the timeout, :func:`CLBNode.is_done_draining` returns
        `True`.
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1', drained_at=0.0)
        self.assertTrue(node.is_done_draining(now=30, timeout=15))

    def test_done_draining_before_timeout_if_there_are_no_connections(self):
        """
        If there are zero connections, but the node has been in draining less
        than the timeout, :func:`CLBNode.is_done_draining` returns `True`.
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1', drained_at=0.0, connections=0)
        self.assertTrue(node.is_done_draining(now=15, timeout=30))

    def test_not_done_draining_before_timeout_if_no_connection_info(self):
        """
        If connection information is not provided, and the node has been in
        draining less than the timeout, :func:`CLBNode.is_done_draining`
        returns `False`.
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1', drained_at=0.0)
        self.assertFalse(node.is_done_draining(now=15, timeout=30))


class StepResultTests(SynchronousTestCase):
    """
    Tests for :class:`StepResult`.
    """
    def test_ordered(self):
        """
        Step results are ordered; FAILURE > RETRY > SUCCESS.
        """
        self.assertGreater(StepResult.FAILURE, StepResult.RETRY)
        self.assertGreater(StepResult.RETRY, StepResult.SUCCESS)
        self.assertGreater(StepResult.FAILURE, StepResult.SUCCESS)
        self.assertEqual(max([StepResult.SUCCESS,
                              StepResult.SUCCESS,
                              StepResult.SUCCESS]),
                         StepResult.SUCCESS)
        self.assertEqual(max([StepResult.SUCCESS,
                              StepResult.RETRY,
                              StepResult.SUCCESS]),
                         StepResult.RETRY)
        self.assertEqual(max([StepResult.FAILURE,
                              StepResult.SUCCESS,
                              StepResult.SUCCESS,
                              StepResult.RETRY]),
                         StepResult.FAILURE)
