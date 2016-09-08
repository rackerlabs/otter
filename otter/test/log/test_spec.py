"""
Tests for log_spec.py
"""
import json

from toolz.dicttoolz import assoc, dissoc

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.model import DesiredServerGroupState

from otter.log.spec import (
    SpecificationObserverWrapper,
    get_validated_event,
    split_cf_messages,
    split_execute_convergence,
    split_list_servers
)
from otter.test.utils import CheckFailureValue
from otter.util.fp import raise_


class SpecificationObserverWrapperTests(SynchronousTestCase):
    """
    Tests for `SpecificationObserverWrapper`
    """

    def setUp(self):
        """
        Sample delegating observer
        """
        self.e = []

        def observer(event):
            self.e.append(event)

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
            [{'message': ('Launching {num_servers} servers', ),
              'num_servers': 2,
              'otter_msg_type': 'launch-servers'}])

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
            [{'original_event': {'message': ("something-bad",), 'a': 'b'},
              'isError': True,
              'failure': CheckFailureValue(ValueError('hm')),
              'why': 'Error validating event',
              'message': ()}])

    def test_event_gets_split(self):
        """
        The observer might emit multiple events if the original event gets
        split.
        """
        message = {'message': ("launch-servers",), "num_servers": 2}
        wrapper = SpecificationObserverWrapper(
            self.observer, lambda e: [e, e.copy()])
        wrapper(message)
        self.assertEqual(self.e, [message, message])


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

    def test_callable_spec_split_events(self):
        """
        Event dictionaries returned will have a field tracking how many events
        the original event was split into.
        """
        e = {'isError': True, 'why': 'foo-bar', 'ab': 'cd'}
        specs = {'foo-bar': lambda e: [(e, e['ab']), (e.copy(), 'another')]}
        self.assertEqual(
            get_validated_event(e, specs),
            [{'why': 'cd',
              'isError': True,
              'otter_msg_type': 'foo-bar',
              'ab': 'cd',
              'split_message': '1 of 2'},
             {'why': 'another',
              'isError': True,
              'otter_msg_type': 'foo-bar',
              'ab': 'cd',
              'split_message': '2 of 2'}])


class ExecuteConvergenceSplitTests(SynchronousTestCase):
    """
    Tests for splitting "execute-convergence" type events
    (e.g. :func:`split_execute_convergence`)
    """
    def setUp(self):
        """
        Set up a desired group state to use for desired, so that serializing
        objects can be tested.
        """
        self.state = DesiredServerGroupState(
            server_config='config', capacity=1)

    def test_split_out_servers_if_servers_longer(self):
        """
        If the 'servers' parameter is longer than the 'lb_nodes' parameter,
        and the event is otherwise sufficiently small, 'servers' is the
        param that gets split into another message.
        """
        event = {'hi': 'there', 'desired': self.state, 'steps': ['steps'],
                 'lb_nodes': ['1', '2', '3'], 'servers': ['1', '2', '3', '4']}
        message = "Executing convergence"

        # assume that removing 'lb_nodes' would make it the perfect length, but
        # since 'servers' is bigger, it's the thing that gets removed.
        length = len(
            json.dumps({k: event[k] for k in event if k != 'lb_nodes'},
                       default=repr))

        result = split_execute_convergence(event.copy(), max_length=length)
        expected = [
            (dissoc(event, 'servers'), message),
            (dissoc(event, 'desired', 'steps', 'lb_nodes'), message)
        ]

        self.assertEqual(result, expected)

    def test_split_out_lb_nodes_if_lb_nodes_longer(self):
        """
        If the 'lb_nodes' parameter is longer than the 'servers' parameter,
        and the event is otherwise sufficiently small, 'lb_nodes' is the
        param that gets split into another message.
        """
        event = {'hi': 'there', 'desired': self.state, 'steps': ['steps'],
                 'lb_nodes': ['1', '2', '3', '4'], 'servers': ['1', '2', '3']}
        message = "Executing convergence"

        # assume that removing 'servers' would make it the perfect length, but
        # since 'lb_nodes' is bigger, it's the thing that gets removed.
        length = len(
            json.dumps({k: event[k] for k in event if k != 'servers'},
                       default=repr),)

        result = split_execute_convergence(event.copy(), max_length=length)
        expected = [
            (dissoc(event, 'lb_nodes'), message),
            (dissoc(event, 'desired', 'steps', 'servers'), message)
        ]

        self.assertEqual(result, expected)

    def test_split_out_both_servers_and_lb_nodes_if_too_long(self):
        """
        Both 'lb_nodes' and 'servers' are split out if the event is too long
        to accomodate both.  The longest one is removed first.
        """
        event = {'hi': 'there', 'desired': self.state, 'steps': ['steps'],
                 'lb_nodes': ['1', '2', '3', '4'], 'servers': ['1', '2', '3']}
        message = "Executing convergence"

        short_event = {k: event[k] for k in event
                       if k not in ('servers', 'lb_nodes')}
        result = split_execute_convergence(
            event.copy(),
            max_length=len(json.dumps(short_event, default=repr)) + 5)

        expected = [
            (short_event, message),
            (dissoc(event, 'desired', 'steps', 'servers'), message),
            (dissoc(event, 'desired', 'steps', 'lb_nodes'), message)
        ]

        self.assertEqual(result, expected)

    def test_split_servers_into_multiple_if_servers_too_long(self):
        """
        Both 'servers' is too long to even fit in one event, split the servers
        list, so there are more than 2 events returned.
        """
        def event(servers):
            return {'hi': 'there', "servers": servers}

        message = "Executing convergence"
        result = split_execute_convergence(
            dict(lb_nodes=[], **event([str(i) for i in range(5)])),
            max_length=len(json.dumps(event(['0', '1']))))

        expected = [
            ({'hi': 'there', 'lb_nodes': []}, message),
            (event(['0', '1']), message),
            (event(['2']), message),
            (event(['3', '4']), message),
        ]

        self.assertEqual(result, expected)


class CFMessageSplitTests(SynchronousTestCase):
    """
    Tests for splitting cf message type events
    (e.g. :func:`split_cf_messages`)
    """
    def test_no_need_to_split_if_below_length(self):
        """
        Do not split the event if the message is sufficiently short.  However,
        do format it so that the list becomes a comma-separated string.
        """
        message = 'Hello {there} human being {punctuation}'
        event = {'there': [1, 2, 3, 4], 'punctuation': '!', 'extra': 'unused'}
        result = split_cf_messages(message, 'there')(event)
        self.assertEqual(result,
                         [(assoc(event, 'there', '1, 2, 3, 4'), message)])

    def test_no_split_on_empty_field(self):
        """
        Do not split the event the field is an empty list, even if it is too
        long.
        """
        message = 'Hello {there} human being {punctuation}'
        event = {'there': [], 'punctuation': '!', 'extra': 'unused'}
        result = split_cf_messages(message, 'there', max_length=5)(event)
        self.assertEqual(result, [(assoc(event, 'there', ''), message)])

    def test_split_only_var_key(self):
        """
        Only the values for the specified key will be split, no matter how long
        the other keys are.
        """
        message = 'x: {x}, y: {y}'
        event = {'x': '123', 'y': '12345'}
        result = split_cf_messages(message, 'x', max_length=14)(event)
        self.assertEqual(
            result,
            [(assoc(event, 'x', '1'), message),
             (assoc(event, 'x', '2'), message),
             (assoc(event, 'x', '3'), message)])


class SplitListServersTests(SynchronousTestCase):
    """
    tests for splitting list servers log
    """

    def test_small(self):
        """
        Events whose response_body len is maxlength will return only that event
        unchanged
        """
        event = split_list_servers(
            {"response_body": {"servers": ["small", "part"]}}, 100)
        self.assertEqual(
            event,
            [({"response_body": '{"servers": ["small", "part"]}'},
              "Listing server details succeeded")])

    def test_split(self):
        """
        Events with response_body len > maxlength will be split into smaller
        events
        """
        event = {"foo": "bar", "response_body": {"servers": range(10)}}
        msg = "Listing server details succeeded"
        self.assertEqual(
            split_list_servers(event, len(json.dumps({"servers": range(5)}))),
            [({"foo": "bar",
               "response_body": '{"servers": [0, 1, 2, 3, 4]}'}, msg),
             ({"foo": "bar",
               "response_body": '{"servers": [5, 6, 7, 8, 9]}'}, msg)])
