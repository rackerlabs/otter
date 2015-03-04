"""
Tests for log_spec.py
"""

from twisted.trial.unittest import SynchronousTestCase

from otter.log.spec import SpecificationObserverWrapper


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
            {'message': ('Launching 2 servers', ),
             'otter_msg_type': 'launch-servers'})

    def test_error_validating_observer(self):
        """
        The observer returned replaces event with error if it fails to
        type check
        """


class GetValidatedEventTests(SynchronousTestCase):
    """
    Tests for `get_validated_event`
    """

    def setUp(self):
        self.event = {}

    def test_error_not_found(self):
        """
        Nothing is changed if Error-based event is not found in msg_types
        """

    def test_error_why_is_changed(self):
        """
        Error-based event's why is changed if found in msg_types.
        otter_msg_type is added
        """

    def test_error_invalid(self):
        """
        If any of the fields in error-based event is invalid, it raises
        `ValueError`. Event is not modified
        """

    def test_error_details_invalid(self):
        """
        If Error-based's details have invalid fields, it raises ValueError.
        Event is not modified
        """

    def test_msg_not_found(self):
        """
        Event is not changed if msg_type is not found
        """

    def test_message_is_changed(self):
        """
        Event's message is changed with msg type if found.
        otter_msg_type is added
        """

    def test_msg_invalid(self):
        """
        Raises `ValueError` if any of the fields is invalid
        """

