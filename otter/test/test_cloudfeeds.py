"""
Tests for otter.cloudfeeds
"""

from twisted.trial.unittest import SynchronousTestCase

from otter.log.cloudfeeds import (
    UnsuitableMessage,
    add_event,
    add_event_to_cloud_feed,
    sanitize_event
)
from otter.test.utils import mock_log


class SanitizeEventsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.cloudfeeds.sanitize_events`
    """

    def setUp(self):  # noqa
        """
        Sample event and CF event
        """
        self.event = {
            "scaling_group_id": "gid",
            "policy_id": "pid",
            "webhook_id": "wid",
            "username": "abc",
            "desired_capacity": 5,
            "current_capacity": 3,
            "message": "human"
        }
        self.exp_cf_event = {
            "scalingGroupId": "gid",
            "policyId": "pid",
            "webhookId": "wid",
            "username": "abc",
            "desiredCapacity": 5,
            "currentCapacity": 3,
            "message": "human"
        }

    def _check_santized_event(self, event):
        """
        Ensure it has only CF keys
        """
        self.assertLessEqual(set(event.keys()), set(self.exp_cf_event))
        for key, value in self.exp_cf_event.items():
            if key in event:
                self.assertEqual(event[key], value)

    def test_all_cf_keys(self):
        """
        All CF keys are captured. Others are ignored
        """
        self.event['more'] = 'stuff'
        se, err = sanitize_event(self.event)
        self._check_santized_event(se)
        self.assertFalse(err)

    def test_subset_cf_keys(self):
        """
        Does not expect all CF keys to be there in event
        """
        del self.event['username'], self.event['policy_id']
        se, err = sanitize_event(self.event)
        self._check_santized_event(se)
        self.assertFalse(err)

    def test_error(self):
        """
        returns error=True if event has isError=True
        """
        self.event['isError'] = True
        se, err = sanitize_event(self.event)
        self._check_santized_event(se)
        self.assertTrue(err)

    def test_unsuitable_msg(self):
        """
        Raises UnsuitableMessage if message contains traceback or exception
        """
        self.event['isError'] = True

        self.event['message'] = 'some traceback'
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)

        self.event['message'] = 'some exception'
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)
