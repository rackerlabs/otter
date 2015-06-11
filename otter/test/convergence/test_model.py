"""
Tests for convergence models.
"""
from uuid import uuid4

from characteristic import attributes

from pyrsistent import freeze, pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from zope.interface import implementer

from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    DRAINING_METADATA,
    IDrainable,
    ILBDescription,
    ILBNode,
    NovaServer,
    ServerState,
    _private_ipv4_addresses,
    _servicenet_address,
    get_service_metadata,
    generate_metadata,
    group_id_from_metadata
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
        :func:`group_id_from_metadata` returns the group ID from
        metadata no matter if it's old style or new style.
        """
        for key in ("rax:autoscale:group:id", "rax:auto_scaling_group_id"):
            self.assertEqual(
                group_id_from_metadata({key: "group_id"}),
                "group_id")

    def test_invalid_group_id_key_returns_none(self):
        """
        If there is no group ID key, either old or new style,
        :func:`NovaServer.group_id_from_metadata` returns `None`.
        """
        for key in (":rax:autoscale:group:id", "rax:autoscaling_group_id",
                    "completely_wrong"):
            self.assertIsNone(
                group_id_from_metadata({key: "group_id"}))

        self.assertIsNone(group_id_from_metadata({}))

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

        self.assertEqual(generate_metadata('group_id', lbs),
                         expected)


class ToNovaServerTests(SynchronousTestCase):
    """
    Tests for :func:`NovaServer.from_server_details_json`
    """
    def setUp(self):
        """
        Sample servers
        """
        self.createds = [('2020-10-10T10:00:00Z', 1602324000),
                         ('2020-10-20T11:30:00Z', 1603193400)]
        self.links = [
            [{'href': 'link1', 'rel': 'self'},
             {'href': 'otherlink1', 'rel': 'bookmark'}],
            [{'href': 'link2', 'rel': 'self'},
             {'href': 'otherlink2', 'rel': 'bookmark'}]
        ]
        self.servers = [{'id': 'a',
                         'status': 'ACTIVE',
                         'created': self.createds[0][0],
                         'image': {'id': 'valid_image'},
                         'flavor': {'id': 'valid_flavor'},
                         'links': self.links[0]},
                        {'id': 'b',
                         'status': 'BUILD',
                         'image': {'id': 'valid_image'},
                         'flavor': {'id': 'valid_flavor'},
                         'created': self.createds[1][0],
                         'addresses': {'private': [{'addr': u'10.0.0.1',
                                                    'version': 4}]},
                         'links': self.links[1]}]

    def test_without_address(self):
        """
        Handles server json that does not have "addresses" in it.
        """
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_without_private(self):
        """
        Creates server that does not have private/servicenet IP in it.
        """
        self.servers[0]['addresses'] = {'public': 'p'}
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_with_servicenet(self):
        """
        Create server that has servicenet IP in it.
        """
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[1]),
            NovaServer(id='b',
                       state=ServerState.BUILD,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[1][1],
                       servicenet_address='10.0.0.1',
                       links=freeze(self.links[1]),
                       json=freeze(self.servers[1])))

    def test_without_image_id(self):
        """
        Create server that has missing image in it in various ways.
        (for the case of BFV)
        """
        for image in ({}, {'id': None}):
            self.servers[0]['image'] = image
            self.assertEqual(
                NovaServer.from_server_details_json(self.servers[0]),
                NovaServer(id='a',
                           state=ServerState.ACTIVE,
                           image_id=None,
                           flavor_id='valid_flavor',
                           created=self.createds[0][1],
                           servicenet_address='',
                           links=freeze(self.links[0]),
                           json=freeze(self.servers[0])))
        del self.servers[0]['image']
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id=None,
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_with_lb_metadata(self):
        """
        Create a server that has load balancer config metadata in it.
        The only desired load balancers created are the ones with valid
        data.
        """
        self.servers[0]['metadata'] = {
            # correct clb config
            'rax:autoscale:lb:CloudLoadBalancer:1':
            '[{"port":80},{"port":90}]',

            # invalid because there is no port
            "rax:autoscale:lb:CloudLoadBalancer:2": '[{}]',
            # two correct lbconfigs and one incorrect one
            'rax:autoscale:lb:CloudLoadBalancer:3':
            '[{"port":80},{"bad":"1"},{"port":90}]',
            # a dictionary instead of a list
            'rax:autoscale:lb:CloudLoadBalancer:4': '{"port": 80}',
            # not even valid json
            'rax:autoscale:lb:CloudLoadBalancer:5': 'invalid json string'
        }
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       desired_lbs=pset([
                           CLBDescription(lb_id='1', port=80),
                           CLBDescription(lb_id='1', port=90)]),
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_lbs_from_metadata_ignores_unsupported_lb_types(self):
        """
        Creating from server json ignores unsupported LB types
        """
        self.servers[0]['metadata'] = {
            "rax:autoscale:lb:RackConnect:{0}".format(uuid4()): None,
            "rax:autoscale:lb:Neutron:456": None
        }
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       desired_lbs=pset(),
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_draining_from_metadata_trumps_active_build_nova_states(self):
        """
        If a draining key and value are in the metadata, the server is in
        DRAINING state so long as the Nova vm state is either ACTIVE or BUILD.
        """
        self.servers[0]['metadata'] = dict([DRAINING_METADATA])

        for status in ("ACTIVE", "BUILD"):
            self.servers[0]['status'] = status
            self.assertEqual(
                NovaServer.from_server_details_json(self.servers[0]),
                NovaServer(id='a',
                           state=ServerState.DRAINING,
                           image_id='valid_image',
                           flavor_id='valid_flavor',
                           created=self.createds[0][1],
                           desired_lbs=pset(),
                           servicenet_address='',
                           links=freeze(self.links[0]),
                           json=freeze(self.servers[0])))

    def test_draining_state_invalid_values(self):
        """
        If a draining key is in the metadata, but the value is invalid, the
        server is not recognized to be in DRAINING state and will just go
        with the Nova vm state.
        """
        self.servers[0]['metadata'] = {DRAINING_METADATA[0]: "meh"}
        self.assertEqual(
            NovaServer.from_server_details_json(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       desired_lbs=pset(),
                       servicenet_address='',
                       links=freeze(self.links[0]),
                       json=freeze(self.servers[0])))

    def test_error_and_deleted_nova_state_trumps_draining_from_metadata(self):
        """
        If a draining key and value are in the metadata, but the Nova vm state
        is DELETED, then the server is in DELETED state, not DRAINING state.
        """
        self.servers[0]['metadata'] = dict([DRAINING_METADATA])
        for status, state in (("ERROR", ServerState.ERROR),
                              ("DELETED", ServerState.DELETED)):
            self.servers[0]['status'] = status
            self.assertEqual(
                NovaServer.from_server_details_json(self.servers[0]),
                NovaServer(id='a',
                           state=state,
                           image_id='valid_image',
                           flavor_id='valid_flavor',
                           created=self.createds[0][1],
                           desired_lbs=pset(),
                           servicenet_address='',
                           links=freeze(self.links[0]),
                           json=freeze(self.servers[0])))


class IPAddressTests(SynchronousTestCase):
    """
    Tests for utility functions that extract IP addresses from server
    dicts.
    """
    def setUp(self):
        """
        Set up a bunch of addresses and a server dict.
        """
        self.addresses = {
            'private': [
                {'addr': '192.168.1.1', 'version': 4},
                {'addr': '10.0.0.1', 'version': 4},
                {'addr': '10.0.0.2', 'version': 4},
                {'addr': '::1', 'version': 6}
            ],
            'public': [
                {'addr': '50.50.50.50', 'version': 4},
                {'addr': '::::', 'version': 6}
            ]}
        self.server_dict = {'addresses': self.addresses}

    def test_private_ipv4_addresses(self):
        """
        :func:`_private_ipv4_addresses` returns all private IPv4 addresses
        from a complete server body.
        """
        result = _private_ipv4_addresses(self.server_dict)
        self.assertEqual(result, ['192.168.1.1', '10.0.0.1', '10.0.0.2'])

    def test_no_private_ip_addresses(self):
        """
        :func:`_private_ipv4_addresses` returns an empty list if the given
        server has no private IPv4 addresses.
        """
        del self.addresses["private"]
        result = _private_ipv4_addresses(self.server_dict)
        self.assertEqual(result, [])

    def test_servicenet_address(self):
        """
        :func:`_servicenet_address` returns the correct ServiceNet
        address, which is the first IPv4 address in the ``private``
        group in the 10.x.x.x range.

        It even does this when there are other addresses in the
        ``private`` group. This happens when the tenant specifies
        their own network named ``private``.
        """
        self.assertEqual(_servicenet_address(self.server_dict), "10.0.0.1")

    def test_no_servicenet_address(self):
        """
        :func:`_servicenet_address` returns :data:`None` if the server has no
        ServiceNet address.
        """
        del self.addresses["private"]
        self.assertEqual(_servicenet_address(self.server_dict), "")
