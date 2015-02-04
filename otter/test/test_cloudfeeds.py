"""
Tests for otter.cloudfeeds
"""

from functools import partial

from effect import Effect, TypeDispatcher
from effect.twisted import deferred_performer

import mock

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.http import TenantScope, has_code, service_request
from otter.log.cloudfeeds import (
    CloudFeedsObserver,
    UnsuitableMessage,
    add_event,
    prepare_request,
    request_format,
    sanitize_event
)
from otter.test.utils import CheckFailure, mock_log
from otter.util.retry import (
    ShouldDelayAndRetry,
    exponential_backoff_interval,
    retry_times
)


def sample_event_pair():
    """
    Sample pair of event dict that observer gets and its corresponding
    cloud feed event
    """
    return {
        "scaling_group_id": "gid",
        "policy_id": "pid",
        "webhook_id": "wid",
        "username": "abc",
        "desired_capacity": 5,
        "current_capacity": 3,
        "message": ("human", ),
        "time": 0
    }, {
        "scalingGroupId": "gid",
        "policyId": "pid",
        "webhookId": "wid",
        "username": "abc",
        "desiredCapacity": 5,
        "currentCapacity": 3,
        "message": "human"
    }


class SanitizeEventTests(SynchronousTestCase):
    """
    Tests for :func:`otter.cloudfeeds.sanitize_events`
    """

    def setUp(self):  # noqa
        """
        Sample event and CF event
        """
        self.event, self.exp_cf_event = sample_event_pair()

    def _check_santized_event(self, exp_err):
        """
        Ensure it has only CF keys
        """
        se, err, _time = sanitize_event(self.event)
        self.assertLessEqual(set(se.keys()), set(self.exp_cf_event))
        self.assertEqual(err, exp_err)
        self.assertEqual(_time, '1970-01-01T00:00:00')
        for key, value in self.exp_cf_event.items():
            if key in se:
                self.assertEqual(se[key], value)
        return se

    def test_all_cf_keys(self):
        """
        All CF keys are captured. Others are ignored
        """
        self.event['more'] = 'stuff'
        self._check_santized_event(False)

    def test_subset_cf_keys(self):
        """
        Does not expect all CF keys to be there in event
        """
        del self.event['username'], self.event['policy_id']
        self._check_santized_event(False)

    def test_error(self):
        """
        returns error=True if event has isError=True
        """
        self.event['isError'] = True
        self._check_santized_event(True)

    def test_unsuitable_msg(self):
        """
        Raises UnsuitableMessage if message contains traceback or exception
        """
        self.event['isError'] = True

        self.event['message'] = ('some traceback', )
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)

        self.event['message'] = ('some exception', )
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)

    def test_formats_message(self):
        """
        message in event dict is formatted
        """
        self.event['message'] = ('abc {a},{b}', )
        self.event['a'] = 'a1'
        self.event['b'] = 'b1'
        self.exp_cf_event['message'] = 'abc a1,b1'
        self._check_santized_event(False)


class EventTests(SynchronousTestCase):
    """
    Tests for :func:`otter.log.cloudfeeds.add_event` :func:`prepare_request`
    """

    def setUp(self):  # noqa
        """
        Sample event and request format
        """
        self.event, self.cf_event = sample_event_pair()
        self.fmt = {'entry': {'content': {'event': {'type': 'INFO',
                                                    'product': {}}}}}

    def test_add_event(self):
        """
        add_event pushes event by calling cloud feed with retries
        """
        log = object()

        def prep_req(*args):
            if args != (request_format, self.cf_event, False,
                        '1970-01-01T00:00:00', 'ord'):
                raise Exception('bad')
            return 'req'

        eff = add_event(self.event, 'tid', 'ord', log, prep_req)

        # effect scoped on on tenant id
        self.assertIs(type(eff.intent), TenantScope)
        self.assertEqual(eff.intent.tenant_id, 'tid')

        # Wrapped effect is retry
        eff = eff.intent.effect
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))

        # effect wrapped in retry is ServiceRequest
        eff = eff.intent.effect
        self.assertEqual(
            eff,
            service_request(
                ServiceType.CLOUD_FEEDS, 'POST', 'autoscale/events',
                data='req', log=log, success_pred=has_code(201)))

    def _check_request(self, req, ev_type):
        """
        Check request matches with event type
        """
        self.assertEqual(
            req,
            {'entry': {
                'content': {
                    'event': {
                        'region': 'ord', 'eventTime': 'ts',
                        'id': 'uuid', 'product': {'a': 'b'},
                        'type': ev_type
                    }
                }
            }})

    def test_prepare_request(self):
        """
        `prepare_request` returns formatted request
        """
        req = prepare_request(self.fmt, {'a': 'b'}, False, 'ts', 'ord',
                              lambda: 'uuid')
        self._check_request(req, 'INFO')

    def test_prepare_request_error(self):
        """
        `prepare_request` returns formatted request with error in type
        """
        req = prepare_request(self.fmt, {'a': 'b'}, True, 'ts', 'ord',
                              lambda: 'uuid')
        self._check_request(req, 'ERROR')


class CloudFeedsObserverTests(SynchronousTestCase):
    """
    Tests for :obj:`CloudFeedsObserver`
    """

    def setUp(self):  # noqa
        """
        Building sample observer
        """
        self.reactor = object()
        self.authenticator = object()
        self.service_configs = {'service': 'configs'}
        self.log = mock_log()
        self.make_cf = partial(
            CloudFeedsObserver, reactor=self.reactor,
            authenticator=self.authenticator, tenant_id='tid',
            region='ord', service_configs=self.service_configs,
            log=self.log)

    def test_no_cloud_feed(self):
        """
        Event without `cloud_feed` in it is ignored
        """
        nocall = mock.NonCallableMock()  # ensure it is not going to be called
        cf = self.make_cf(add_event=nocall, get_disp=nocall)
        cf({'cloud_feed': False})
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.log.err.called)

    def test_event_added(self):
        """
        Event is added to cloud feed
        """
        class AddEvent(object):
            pass

        add_event_performer = deferred_performer(
            lambda d, i: succeed('performed'))

        cf = self.make_cf(
            add_event=lambda *a: Effect(AddEvent()),
            get_disp=lambda *a: TypeDispatcher(
                {AddEvent: add_event_performer}))
        d = cf({'event': 'dict', 'cloud_feed': True, 'message': ('m', )})

        self.assertEqual(self.successResultOf(d), 'performed')
        self.assertFalse(self.log.err.called)

    def test_perform_fails(self):
        """
        If performing effect to add event fails, error is logged
        """
        class AddEvent(object):
            pass

        add_event_performer = deferred_performer(
            lambda d, i: fail(ValueError('bad')))

        cf = self.make_cf(
            add_event=lambda *a: Effect(AddEvent()),
            get_disp=lambda *a: TypeDispatcher(
                {AddEvent: add_event_performer}))
        d = cf({'event': 'dict', 'cloud_feed': True, 'message': ('m', )})

        self.successResultOf(d)
        # log doesn't have cloud_feed in it
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "Failed to add event", event='dict',
            system='otter.cloud_feed', cf_msg='m')

    def test_unsuitable_msg_logs(self):
        """
        If add_event raises `UnsuitableMessage`, it is not added and
        error is logged
        """
        def add_event(*a):
            raise UnsuitableMessage("bad")

        cf = self.make_cf(add_event=add_event, get_disp=lambda *a: 1 / 0)
        cf({'event': 'dict', 'cloud_feed': True, 'message': ('m', )})
        self.log.err.assert_called_once_with(
            None, ('Tried to add unsuitable message in cloud feeds: '
                   '{unsuitable_message}'),
            unsuitable_message='bad', event='dict', system='otter.cloud_feed',
            cf_msg='m')
