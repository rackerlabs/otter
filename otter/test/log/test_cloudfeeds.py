"""
Tests for otter.cloudfeeds
"""
from functools import partial

from effect import Effect, TypeDispatcher
from effect.testing import perform_sequence

import mock

from twisted.internet.defer import fail, succeed
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase
from twisted.web.client import ResponseFailed

from txeffect import deferred_performer

from otter.cloud_client import TenantScope, has_code, service_request
from otter.constants import ServiceType
from otter.log.cloudfeeds import (
    CloudFeedsObserver,
    UnsuitableMessage,
    add_event,
    cf_err, cf_fail, cf_msg,
    prepare_request,
    request_format,
    sanitize_event
)
from otter.log.formatters import LogLevel
from otter.log.intents import Log, LogErr
from otter.test.utils import (
    CheckFailure,
    mock_log,
    nested_sequence,
    retry_sequence,
    stub_pure_response
)
from otter.util.fp import raise_
from otter.util.http import APIError
from otter.util.retry import (
    Retry,
    ShouldDelayAndRetry,
    exponential_backoff_interval
)


class CFHelperTests(SynchronousTestCase):
    """
    Tests for cf_* functions
    """

    def test_cf_msg(self):
        """
        `cf_msg` returns Effect with `Log` intent with cloud_feed=True
        """
        seq = [
            (Log('message', dict(cloud_feed=True, a=2, b=3)),
                lambda _: 'logged')
        ]
        self.assertEqual(perform_sequence(seq, cf_msg('message', a=2, b=3)),
                         'logged')

    def test_cf_err(self):
        """
        `cf_err` returns Effect with `Log` intent with cloud_feed=True
        and isError=True
        """
        seq = [
            (Log('message', dict(isError=True, cloud_feed=True, a=2, b=3)),
                lambda _: 'logged')
        ]
        self.assertEqual(perform_sequence(seq, cf_err('message', a=2, b=3)),
                         'logged')

    def test_cf_fail(self):
        """
        `cf_err` returns Effect with `LogErr` intent with cloud_feed=True
        """
        f = object()
        seq = [
            (LogErr(f, 'message', dict(cloud_feed=True, a=2, b=3)),
                lambda _: 'logged')
        ]
        self.assertEqual(
            perform_sequence(seq, cf_fail(f, 'message', a=2, b=3)),
            'logged')


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
        "tenant_id": "tid",
        "level": LogLevel.INFO,
        "cloud_feed_id": '00000000-0000-0000-0000-000000000000'
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
        se, err, _time, tenant_id, event_id = sanitize_event(self.event)
        self.assertLessEqual(set(se.keys()), set(self.exp_cf_event))
        self.assertEqual(err, exp_err)
        self.assertEqual(_time, '1970-01-01T00:00:00Z')
        self.assertEqual(tenant_id, 'tid')
        self.assertEqual(event_id, '00000000-0000-0000-0000-000000000000')
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

        self.event['level'] = LogLevel.INFO
        del self.event['tenant_id']
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

    def _get_request(self, _type, _id, tenant_id):
        """
        Sample formatted request
        """
        self.req['entry']['content']['event']['type'] = _type
        self.req['entry']['content']['event']['id'] = _id
        self.req['entry']['content']['event']['tenantId'] = tenant_id
        return self.req

    def _perform_add_event(self, response_sequence):
        """
        Given a sequence of functions that take an intent and returns a
        response (or raises an exception), perform :func:`add_event` and
        return the result.
        """
        log = object()
        eff = add_event(self.event, 'tid', 'ord', log)
        uid = '00000000-0000-0000-0000-000000000000'

        svrq = service_request(
            ServiceType.CLOUD_FEEDS, 'POST', 'autoscale/events',
            headers={
                'content-type': ['application/vnd.rackspace.atom+json']},
            data=self._get_request('INFO', uid, 'tid'), log=log,
            success_pred=has_code(201),
            json_response=False)

        seq = [
            (TenantScope(mock.ANY, 'tid'), nested_sequence([
                retry_sequence(
                    Retry(effect=svrq, should_retry=ShouldDelayAndRetry(
                        can_retry=mock.ANY,
                        next_interval=exponential_backoff_interval(2))),
                    response_sequence
                )
            ]))
        ]

        return perform_sequence(seq, eff)

    def test_add_event_succeeds_if_request_succeeds(self):
        """
        Adding an event succeeds without retrying if the service request
        succeeds.  Testing what response code causes a service request to
        succeeds is beyond the scope of this test.
        """
        body = "<some xml>"
        resp = stub_pure_response(body, 201)
        response = [lambda _: (resp, body)]
        self.assertEqual(self._perform_add_event(response), (resp, body))

    def test_add_event_only_retries_5_times_on_non_4xx_api_errors(self):
        """
        Attempting to add an event is only retried up to a maximum of 5 times,
        and only if it's not an 4XX APIError.
        """
        responses = [
            lambda _: raise_(Exception("oh noes!")),
            lambda _: raise_(ResponseFailed(Failure(Exception(":(")))),
            lambda _: raise_(APIError(code=100, body="<some xml>")),
            lambda _: raise_(APIError(code=202, body="<some xml>")),
            lambda _: raise_(APIError(code=301, body="<some xml>")),
            lambda _: raise_(APIError(code=501, body="<some xml>")),
        ]
        with self.assertRaises(APIError) as cm:
            self._perform_add_event(responses)

        self.assertEqual(cm.exception.code, 501)

    def test_add_event_bails_on_4xx_api_errors(self):
        """
        If CF returns a 4xx error, adding an event is not retried.
        """
        response = [lambda _: raise_(APIError(code=409, body="<some xml>"))]
        self.assertRaises(APIError, self._perform_add_event, response)

    def test_prepare_request_error(self):
        """
        `prepare_request` returns formatted request with error in type
        """
        req = prepare_request(
            request_format, self.cf_event, True, "1970-01-01T00:00:00Z",
            'ord', 'tid', 'uuid')
        self.assertEqual(req, self._get_request('ERROR', 'uuid', 'tid'))


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
