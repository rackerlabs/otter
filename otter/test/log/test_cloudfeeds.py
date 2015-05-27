"""
Tests for otter.cloudfeeds
"""

import uuid
from functools import partial

from effect import Effect, TypeDispatcher

import mock

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from txeffect import deferred_performer

from otter.cloud_client import TenantScope, has_code, service_request
from otter.constants import ServiceType
from otter.log.cloudfeeds import (
    CloudFeedsObserver,
    UnsuitableMessage,
    add_event,
    cf_err, cf_fail, cf_msg,
    get_cf_observer,
    prepare_request,
    request_format,
    sanitize_event
)
from otter.log.formatters import LogLevel
from otter.log.intents import Log, LogErr
from otter.test.utils import CheckFailure, mock_log, patch, resolve_effect
from otter.util.retry import (
    ShouldDelayAndRetry,
    exponential_backoff_interval,
    retry_times
)


class CFHelperTests(SynchronousTestCase):
    """
    Tests for cf_* functions
    """

    def test_cf_msg(self):
        """
        `cf_msg` returns Effect with `Log` intent with cloud_feed=True
        """
        self.assertEqual(
            cf_msg('message', a=2, b=3),
            Effect(Log('message', dict(cloud_feed=True, a=2, b=3)))
        )

    def test_cf_err(self):
        """
        `cf_err` returns Effect with `Log` intent with cloud_feed=True
        and isError=True
        """
        self.assertEqual(
            cf_err('message', a=2, b=3),
            Effect(Log('message', dict(isError=True, cloud_feed=True,
                                       a=2, b=3)))
        )

    def test_cf_fail(self):
        """
        `cf_err` returns Effect with `LogErr` intent with cloud_feed=True
        """
        f = object()
        self.assertEqual(
            cf_fail(f, 'message', a=2, b=3),
            Effect(LogErr(f, 'message', dict(cloud_feed=True, a=2, b=3)))
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
        "time": 0,
        "level": LogLevel.INFO
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
        self.assertEqual(_time, '1970-01-01T00:00:00Z')
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
        returns error=True if event has level is ERROR
        """
        self.event['level'] = LogLevel.ERROR
        self._check_santized_event(True)

    def test_unsuitable_msg(self):
        """
        Raises UnsuitableMessage if message contains traceback or exception
        """
        self.event['level'] = LogLevel.ERROR

        self.event['message'] = ('some traceback', )
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)

        self.event['message'] = ('some exception', )
        self.assertRaises(UnsuitableMessage, sanitize_event, self.event)


class EventTests(SynchronousTestCase):
    """
    Tests for :func:`otter.log.cloudfeeds.add_event` :func:`prepare_request`
    """

    def setUp(self):  # noqa
        """
        Sample event and request format
        """
        self.event, self.cf_event = sample_event_pair()
        self.req = {
            "entry": {
                "@type": "http://www.w3.org/2005/Atom",
                "title": "autoscale",
                "content": {
                    "event": {
                        "@type": "http://docs.rackspace.com/core/event",
                        "id": "",
                        "version": "2",
                        "eventTime": "1970-01-01T00:00:00Z",
                        "type": "INFO",
                        "region": "ord",
                        "product": {
                            "@type": ("http://docs.rackspace.com/event/"
                                      "autoscale"),
                            "serviceCode": "Autoscale",
                            "version": "1",
                            "scalingGroupId": "gid",
                            "policyId": "pid",
                            "webhookId": "wid",
                            "username": "abc",
                            "desiredCapacity": 5,
                            "currentCapacity": 3,
                            "message": "human"
                        }
                    }
                }
            }
        }

    def _get_request(self, _type, _id):
        """
        Sample formatted request
        """
        self.req['entry']['content']['event']['type'] = _type
        self.req['entry']['content']['event']['id'] = _id
        return self.req

    def test_add_event(self):
        """
        add_event pushes event by calling cloud feed with retries
        """
        log = object()
        eff = add_event(self.event, 'tid', 'ord', log)

        # effect is to generate UUID
        self.assertIs(eff.intent.func, uuid.uuid4)
        eff = resolve_effect(eff, uuid.UUID(int=0))
        uid = '00000000-0000-0000-0000-000000000000'

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
                headers={
                    'content-type': ['application/vnd.rackspace.atom+json']},
                data=self._get_request('INFO', uid), log=log,
                success_pred=has_code(201)))

    def test_prepare_request_error(self):
        """
        `prepare_request` returns formatted request with error in type
        """
        req = prepare_request(
            request_format, self.cf_event, True, "1970-01-01T00:00:00Z",
            'ord', 'uuid')
        self.assertEqual(req, self._get_request('ERROR', 'uuid'))


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
            CheckFailure(ValueError), 'cf-add-failure',
            event_data={'event': 'dict'}, system='otter.cloud_feed',
            cf_msg='m')

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
            None, 'cf-unsuitable-message', unsuitable_message='bad',
            event_data={'event': 'dict'}, system='otter.cloud_feed',
            cf_msg='m')

    def test_get_cf_observer(self):
        """
        `get_cf_observer` returns CloudFeedsObserver with observer chain setup
        before creating
        """
        def wrapper(name, observer):
            def _observer(e):
                observer(e + name)
            return _observer

        patch(self, 'otter.log.cloudfeeds.SpecificationObserverWrapper',
              side_effect=partial(wrapper, 'spec'))
        patch(self, 'otter.log.cloudfeeds.PEP3101FormattingWrapper',
              side_effect=partial(wrapper, 'pep'))
        patch(self, 'otter.log.cloudfeeds.ErrorFormattingWrapper',
              side_effect=partial(wrapper, 'error'))

        def cf_observer_called(text):
            self.cf_observer_text = text
        mock_cfo = patch(self, 'otter.log.cloudfeeds.CloudFeedsObserver')
        cfo_class = mock_cfo.return_value
        cfo_class.side_effect = cf_observer_called

        cfo = get_cf_observer(*range(5))

        mock_cfo.assert_called_once_with(
            reactor=0, authenticator=1, tenant_id=2, region=3,
            service_configs=4)

        cfo('test')
        self.assertEqual(self.cf_observer_text, 'testspecpeperror')
