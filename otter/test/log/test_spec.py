"""
Tests for log_spec.py
"""


class SpecificationObserverWrapperTests(SynchronousTestCase):
    """
    Tests for `SpecificationObserverWrapper`
    """

    def returns_validating_observer(self):
        """
        Returns observer that validates event and delgates to given observer
        """


class GetValidatedEventTests(SynchronousTestCase):
    """
    Tests for `get_validated_event`
    """

    def setUp(self):
        self.event = {}

    def test_error_not_found(self):
        """
        Nothing is changed if Error-based event is not found
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

