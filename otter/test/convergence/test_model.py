"""
Tests for convergence models.
"""
from uuid import uuid4

from characteristic import attributes

from pyrsistent import pmap

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
    get_service_metadata
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
        node = CLBNode(node_id='1234', description=self.desc,
                       address='10.1.1.1')
        self.assertFalse(
            node.matches(DummyServer(servicenet_address="10.1.1.1")))

    def test_matches_only_if_server_address_matches_node_address(self):
        """
        :func:`CLBNode.matches` returns True only if the :class:`NovaServer`
        has the same ServiceNet address as the node address
        """
        node = CLBNode(node_id='1234', description=self.desc,
                       address='10.1.1.1')
        self.assertFalse(node.matches(
            NovaServer(id='1', state=ServerState.ACTIVE, created=0.0,
                       servicenet_address="10.1.1.2",
                       image_id='image', flavor_id='flavor')))
        self.assertTrue(node.matches(
            NovaServer(id='1', state=ServerState.ACTIVE, created=0.0,
                       servicenet_address="10.1.1.1",
                       image_id='image', flavor_id='flavor')))

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

    def test_active_if_node_is_enabled(self):
        """
        If the node is ENABLED, :func:`CLBNode.is_active` returns `True`.
        """
        node = CLBNode(node_id='1234', description=self.desc,
                       address='10.1.1.1', drained_at=0.0, connections=1)
        self.assertTrue(node.is_active())

    def test_active_if_node_is_draining(self):
        """
        If the node is DRAINING, :func:`CLBNode.is_active` returns `True`.
        """
        node = CLBNode(node_id='1234', description=self.drain_desc,
                       address='10.1.1.1', drained_at=0.0, connections=1)
        self.assertTrue(node.is_active())

    def test_inactive_if_node_is_disabled(self):
        """
        If the node is DRAINING, :func:`CLBNode.is_active` returns `True`.
        """
        node = CLBNode(node_id='1234',
                       description=CLBDescription(
                           lb_id='12345', port=80,
                           condition=CLBNodeCondition.DISABLED),
                       address='10.1.1.1', drained_at=0.0, connections=1)
        self.assertFalse(node.is_active())


class ServiceMetadataTests(SynchronousTestCase):
    """
    Tests for :func:`get_service_metadata`.
    """
    def test_returns_empty_map_if_metadata_invalid(self):
        """
        If metadata is invalid (a string or otherwise not a dictionary),
        an empty map is returned.
        """
        for invalid in ("string", None, [], object()):
            self.assertEqual(get_service_metadata('autoscale', invalid),
                             pmap())

    def test_skips_invalid_keys_and_mismatching_services(self):
        """
        :func:`get_service_metadata` ignores all keys that do not
        match the service or the `rax:<service>:...` naming scheme.
        """
        metadata = {
            "bleh:rax:autoscale:lb": "fails because starts with bleh",
            "rax:autoscale:lb otherstuff": "fails because space",
            "rax:monitoring:check": "fails because wrong service",
            ":rax:autoscale:lb": "fails because starts with colon",
            "rax:autoscale:lb:": "fails because ends with colon",
            "rax:rax:autoscale:lb:autoscale:lb": "fails because 2x'rax'"
        }
        self.assertEqual(get_service_metadata('autoscale', metadata), pmap())

    def test_creates_dictionary_of_arbitrary_depth(self):
        """
        :func:`get_service_metadata` creates a dictionary of arbitrary depth
        depending on how many colons are in the keys.
        """
        metadata = {
            "rax:autoscale:group:id": "group id",
            "rax:autoscale:lb:CloudLoadBalancer:123": "result1",
            "rax:autoscale:lb:CloudLoadBalancer:234": "result2",
            "rax:autoscale:lb:RackConnectV3:123": "result3",
            "rax:autoscale:lb:RackConnectV3:234": "result4",
            "rax:autoscale:some:other:nested:key": "result5",
            "rax:autoscale:topLevelKey_with_underlines-and-dashes": "result6",
            "rax:autoscale:autoscale:lb": "result7"
        }
        expected = {
            'group': {'id': 'group id'},
            'lb': {
                'CloudLoadBalancer': {'123': 'result1',
                                      '234': 'result2'},
                'RackConnectV3': {'123': 'result3',
                                  '234': 'result4'}
            },
            'some': {'other': {'nested': {'key': 'result5'}}},
            "topLevelKey_with_underlines-and-dashes": "result6",
            'autoscale': {'lb': 'result7'}
        }
        self.assertEqual(get_service_metadata('autoscale', metadata),
                         pmap(expected))


class AutoscaleMetadataTests(SynchronousTestCase):
    """
    Tests for generating and parsing Nova server metadata.
    """
    def test_get_group_id_from_metadata(self):
        """
        :func:`NovaServer.group_id_from_metadata` returns the group ID from
        metadata no matter if it's old style or new style.
        """
        for key in ("rax:autoscale:group:id", "rax:auto_scaling_group_id"):
            self.assertEqual(
                NovaServer.group_id_from_metadata({key: "group_id"}),
                "group_id")

    def test_invalid_group_id_key_returns_none(self):
        """
        If there is no group ID key, either old or new style,
        :func:`NovaServer.group_id_from_metadata` returns `None`.
        """
        for key in (":rax:autoscale:group:id", "rax:autoscaling_group_id",
                    "completely_wrong"):
            self.assertIsNone(
                NovaServer.group_id_from_metadata({key: "group_id"}))

        self.assertIsNone(NovaServer.group_id_from_metadata({}))

    def test_lbs_from_metadata_CLB(self):
        """
        :func:`NovaServer.lbs_from_metadata` returns a set of
        `CLBDescription` objects if the metadata is parsable as a CLB config,
        and ignores the metadata line if unparsable.
        """
        metadata = {
            "rax:autoscale:lb:CloudLoadBalancer:123":
                '[{"port": 80}, {"port": 8080}]',

            # invalid because there is no port
            "rax:autoscale:lb:CloudLoadBalancer:234": '[{}]',
            # invalid because not a list
            "rax:autoscale:lb:CloudLoadBalancer:345": '{"port": 80}',
            # invalid because not JSON
            "rax:autoscale:lb:CloudLoadBalancer:456": 'junk'
        }
        self.assertEqual(
            NovaServer.lbs_from_metadata(metadata),
            pmap({'123': [CLBDescription(lb_id='123', port=80),
                          CLBDescription(lb_id='123', port=8080)]}))

    def test_lbs_from_metadata_ignores_unsupported_lb_types(self):
        """
        :func:`NovaServer.lbs_from_metadata` ignores unsupported LB types
        """
        metadata = {
            "rax:autoscale:lb:RackConnect:{0}".format(uuid4()): None,
            "rax:autoscale:lb:Neutron:456": None
        }
        self.assertEqual(NovaServer.lbs_from_metadata(metadata), pmap())

    def test_generate_metadata(self):
        """
        :func:`NovaServer.lbs_from_metadata` produces a dictionary with
        metadata for the group ID and any load balancers provided.
        """
        lbs = [
            CLBDescription(port=80, lb_id='123'),
            CLBDescription(port=8080, lb_id='123'),
            CLBDescription(port=80, lb_id='234')
        ]
        expected = {
            'rax:autoscale:group:id': 'group_id',
            'rax:auto_scaling_group_id': 'group_id',
            'rax:autoscale:lb:CloudLoadBalancer:123': (
                '[{"port": 80}, {"port": 8080}]'),
            'rax:autoscale:lb:CloudLoadBalancer:234': '[{"port": 80}]'
        }

        self.assertEqual(NovaServer.generate_metadata('group_id', lbs),
                         expected)
