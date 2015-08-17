"""
Tests for log_spec.py
"""

from twisted.trial.unittest import SynchronousTestCase

from otter.log.spec import SpecificationObserverWrapper, get_validated_event
from otter.test.utils import CheckFailureValue, raise_


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

    def test_error_validating_observer(self):
        """
        The observer returned replaces event with error if it fails to
        type check
        """
        wrapper = SpecificationObserverWrapper(
            self.observer, lambda e: raise_(ValueError('hm')))
        wrapper({'message': ("something-bad",), 'a': 'b'})
        self.assertEqual(
            self.e,
            {'original_event': {'message': ("something-bad",), 'a': 'b'},
             'isError': True,
             'failure': CheckFailureValue(ValueError('hm')),
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
        self.assertEqual(get_validated_event(e), [e])

    def test_error_why_is_changed(self):
        """
        Error-based event's why is changed if found in msg_types.
        otter_msg_type is added
        """
        e = {'isError': True, 'why': 'delete-server', 'a': 'b'}
        self.assertEqual(
            get_validated_event(e),
            [{'why': 'Deleting {server_id} server',
              'isError': True, 'a': 'b',
              'otter_msg_type': 'delete-server'}])

    def test_error_no_why_in_event(self):
        """
        If error-based event's does not have "why", then it is not changed
        """
        e = {'isError': True, 'a': 'b'}
        self.assertEqual(get_validated_event(e), [e])

    def test_error_no_why_but_message(self):
        """
        When error-based event does not have "why", then its message is tried
        """
        e = {'isError': True, 'a': 'b', "message": ('delete-server',)}
        self.assertEqual(
            get_validated_event(e),
            [{'message': ('Deleting {server_id} server',), 'isError': True,
              'why': 'Deleting {server_id} server',
              'a': 'b', 'otter_msg_type': 'delete-server'}])

    def test_msg_not_found(self):
        """
        Event is not changed if msg_type is not found
        """
        e = {'message': ('unknown',), 'a': 'b'}
        self.assertEqual(get_validated_event(e), [e])

    def test_message_is_changed(self):
        """
        Event's message is changed with msg type if found.
        otter_msg_type is added
        """
        e = {'message': ('delete-server',), 'a': 'b'}
        self.assertEqual(
            get_validated_event(e),
            [{'message': ('Deleting {server_id} server',),
              'a': 'b', 'otter_msg_type': 'delete-server'}])

    def test_callable_spec(self):
        """
        Spec values can be callable, in which case they will be called with the
        event dict, and their return value will be used as the new `message`.
        """
        e = {"message": ('foo-bar',), 'ab': 'cd'}
        self.assertEqual(
            get_validated_event(e,
                                specs={'foo-bar': lambda e: [(e, e['ab'])]}),
            [{'message': ('cd',),
              'otter_msg_type': 'foo-bar',
              'ab': 'cd'}])

    def test_callable_spec_error(self):
        """
        Spec values will be called for errors as well, and their return will be
        used as the new value for `why`.
        """
        e = {'isError': True, 'why': 'foo-bar', 'ab': 'cd'}
        self.assertEqual(
            get_validated_event(e,
                                specs={'foo-bar': lambda e: [(e, e['ab'])]}),
            [{'why': 'cd',
              'isError': True,
              'otter_msg_type': 'foo-bar',
              'ab': 'cd'}])
