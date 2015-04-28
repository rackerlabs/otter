"""
Tests for log_spec.py
"""

import mock

from twisted.trial.unittest import SynchronousTestCase

from otter.log.spec import SpecificationObserverWrapper, get_validated_event
from otter.test.utils import CheckFailure


class SpecificationObserverWrapperTests(SynchronousTestCase):
    """
    Tests for `SpecificationObserverWrapper`
    """

    def setUp(self):
        """
        Sample delegating observer
        """
        self.e = None

        def observer(event):
            self.e = event

        self.observer = observer

    def test_returns_validating_observer(self):
        """
        Returns observer that gets validated event and delgates
        to given observer
        """
        SpecificationObserverWrapper(self.observer)(
            {'message': ("launch-servers",), "num_servers": 2})
        self.assertEqual(
            self.e,
            {'message': ('Launching {num_servers} servers', ),
             'num_servers': 2,
             'otter_msg_type': 'launch-servers'})

    @mock.patch('otter.log.spec.get_validated_event', side_effect=ValueError)
    def test_error_validating_observer(self, mock_gve):
        """
        The observer returned replaces event with error if it fails to
        type check
        """
        SpecificationObserverWrapper(self.observer)(
            {'message': ("something-bad",)})
        self.assertEqual(
            self.e,
            {'original_message': ("something-bad",),
             'isError': True,
             'failure': CheckFailure(ValueError),
             'why': 'Error validating event',
             'message': ()})


class GetValidatedEventTests(SynchronousTestCase):
    """
    Tests for `get_validated_event`
    """

    def test_error_not_found(self):
        """
        Nothing is changed if Error-based event is not found in msg_types
        """
        e = {'isError': True, 'why': 'unknown', 'a': 'b'}
        self.assertEqual(get_validated_event(e), e)

    def test_error_why_is_changed(self):
        """
        Error-based event's why is changed if found in msg_types.
        otter_msg_type is added
        """
        e = {'isError': True, 'why': 'delete-server', 'a': 'b'}
        self.assertEqual(
            get_validated_event(e),
            {'why': 'Deleting {server_id} server',
             'isError': True, 'a': 'b',
             'otter_msg_type': 'delete-server'})

    def test_error_no_why_in_event(self):
        """
        If error-based event's does not have "why", then it is not changed
        """
        e = {'isError': True, 'a': 'b'}
        self.assertEqual(get_validated_event(e), e)

    def test_msg_not_found(self):
        """
        Event is not changed if msg_type is not found
        """
        e = {'message': ('unknown',), 'a': 'b'}
        self.assertEqual(get_validated_event(e), e)

    def test_message_is_changed(self):
        """
        Event's message is changed with msg type if found.
        otter_msg_type is added
        """
        e = {'message': ('delete-server',), 'a': 'b'}
        self.assertEqual(
            get_validated_event(e),
            {'message': ('Deleting {server_id} server',),
             'a': 'b', 'otter_msg_type': 'delete-server'})
