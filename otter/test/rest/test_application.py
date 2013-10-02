# encoding: utf-8

"""
Tests for :mod:`otter.rest.application`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.rest.otterapp import OtterApp
from otter.rest.decorators import with_transaction_id, log_arguments
from otter.test.rest.request import RequestTestMixin
from otter.test.utils import patch
from otter.util.config import set_config_data
from otter.util.http import (get_autoscale_links, transaction_id,
                             get_new_paginate_query_args)


class LinkGenerationTestCase(TestCase):
    """
    Tests for generating autoscale links
    """

    def setUp(self):
        """
        Set a blank root URL
        """
        self.base_url_patcher = mock.patch(
            "otter.util.http.get_url_root", return_value="")
        self.base_url_patcher.start()

    def tearDown(self):
        """
        Undo blanking the root URL
        """
        self.base_url_patcher.stop()

    def _expected_json(self, url):
        return [
            {
                'rel': 'self',
                'href': url
            }
        ]

    def test_get_only_groups_link(self):
        """
        If only the tenant ID is passed, and the rest of the arguments are
        blank, then the returned base link is /v<api>/<tenant>/groups/
        """
        self.assertEqual(
            get_autoscale_links('11111', api_version='3', format=None),
            '/v3/11111/groups/')

        expected_url = '/v1.0/11111/groups/'
        # test default API
        self.assertEqual(get_autoscale_links('11111', format=None),
                         expected_url)
        # test JSON formatting
        self.assertEqual(get_autoscale_links('11111'),
                         self._expected_json(expected_url))

    def test_get_only_groups_link_for_varying_other_args(self):
        """
        So long as the group ID is not a valid number, we still get the groups
        link /v<api>/<tenant>/groups/
        """
        equivalents = [
            get_autoscale_links('11111', group_id='', format=None),
            get_autoscale_links('11111', policy_id='5', format=None),
            get_autoscale_links('11111', policy_id='', format=None)
        ]
        for equivalent in equivalents:
            self.assertEqual(equivalent, '/v1.0/11111/groups/')

    def test_get_tenant_id_and_group_id(self):
        """
        If only the tenant ID and group ID are passed, and the rest of the
        arguments are blank, then the returned base link is
        /v<api>/<tenant>/groups/<group>
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', api_version='3',
                                format=None),
            '/v3/11111/groups/1/')

        expected_url = '/v1.0/11111/groups/1/'
        # test default API
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', format=None),
            expected_url)
        # test JSON formatting
        self.assertEqual(get_autoscale_links('11111', group_id='1'),
                         self._expected_json(expected_url))

    def test_get_groups_and_group_id_link_for_varying_other_args(self):
        """
        So long as the policy ID is None, we still get the groups
        link /v<api>/<tenant>/groups/<group_id>
        """
        equivalents = [
            get_autoscale_links('11111', group_id='1', webhook_id='1',
                                format=None),
            get_autoscale_links('11111', group_id='1', webhook_id='',
                                format=None),
        ]
        for equivalent in equivalents:
            self.assertEqual(equivalent, '/v1.0/11111/groups/1/')

    def test_get_tenant_id_and_group_id_and_blank_policy_id(self):
        """
        If the tenant ID, the group ID, and an empty policy ID (not None) are
        passed, the returned based link is
        /v<api>/<tenant>/groups/<group>/policies
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="",
                                api_version='3', format=None),
            '/v3/11111/groups/1/policies/')

        expected_url = '/v1.0/11111/groups/1/policies/'
        # test default API
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="",
                                format=None),
            expected_url)
        # test JSON formatting
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id=""),
            self._expected_json(expected_url))

    def test_get_tenant_id_and_group_id_and_policy_id(self):
        """
        If the tenant ID, the group ID, and a policy ID (not blank) are
        passed, the returned based link is
        /v<api>/<tenant>/groups/<group>/policies/<policy>
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="5",
                                api_version='3', format=None),
            '/v3/11111/groups/1/policies/5/')

        expected_url = '/v1.0/11111/groups/1/policies/5/'
        # test default API
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="5",
                                format=None),
            expected_url)
        # test JSON formatting
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="5"),
            self._expected_json(expected_url))

    def test_get_tenant_group_policy_ids_and_blank_webhook_id(self):
        """
        If the tenant ID, the group ID, the policy ID, and an empty wbehook ID
        (not None) are passed, the returned based link is
        /v<api>/<tenant>/groups/<group>/policies/<policy>/webhooks
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id="", api_version='3', format=None),
            '/v3/11111/groups/1/policies/2/webhooks/')

        expected_url = '/v1.0/11111/groups/1/policies/2/webhooks/'
        # test default API
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id="", format=None),
            expected_url)
        # test JSON formatting
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id=""),
            self._expected_json(expected_url))

    def test_get_tenant_group_policy_and_webhook_id(self):
        """
        If the tenant ID, the group ID, the policy ID, and a webhook ID
        (not blank) are passed, the returned based link is
        /v<api>/<tenant>/groups/<group>/policies/<policy>/webhooks/<webhook>
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id="3", api_version='3', format=None),
            '/v3/11111/groups/1/policies/2/webhooks/3/')

        expected_url = '/v1.0/11111/groups/1/policies/2/webhooks/3/'
        # test default API
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id="3", format=None),
            expected_url)
        # test JSON formatting
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="2",
                                webhook_id="3"),
            self._expected_json(expected_url))

    def test_capability_url_included_with_capability_hash(self):
        """
        If a capability_hash parameter is passed in, an extra link is added to
        the JSON blob containing a capability URL.  But in the non-formatted
        URL, nothing changes.
        """
        pairs = [("group_id", "1"), ("policy_id", "2"), ("webhook_id", "3")]
        expected = [
            '/v1.0/11111/groups/1/',
            '/v1.0/11111/groups/1/policies/2/',
            '/v1.0/11111/groups/1/policies/2/webhooks/3/'
        ]
        for i in range(3):
            self.assertEqual(
                get_autoscale_links(
                    '11111', format=None, capability_hash='xxx',
                    **dict(pairs[:(i + 1)])),
                expected[i])

            json_blob = get_autoscale_links(
                '11111', capability_hash='xxx', **dict(pairs[:(i + 1)]))

            self.assertEqual(len(json_blob), 2)
            self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/1/xxx/'},
                          json_blob)

    def test_capability_version(self):
        """
        There is a default capability version of 1, but whatever capability
        version is passed is the one used
        """
        # default version
        json_blob = get_autoscale_links(
            '11111', group_id='1', policy_id='2', webhook_id='3',
            capability_hash='xxx')
        self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/1/xxx/'},
                      json_blob)

        json_blob = get_autoscale_links(
            '11111', group_id='1', policy_id='2', webhook_id='3',
            capability_hash='xxx', capability_version="8")
        self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/8/xxx/'},
                      json_blob)

    def test_capability_urls_unicode_escaped(self):
        """
        Even if unicode path bits are provided, only bytes urls are returned
        """
        self.assertTrue(isinstance(
            get_autoscale_links(u'11111', group_id=u'1', policy_id=u'2',
                                format=None),
            str))
        snowman = get_autoscale_links('☃', group_id='☃', format=None)
        self.assertEqual(snowman, '/v1.0/%E2%98%83/groups/%E2%98%83/')
        self.assertTrue(isinstance(snowman, str))

    def test_query_params(self):
        """
        When query parameters are provided, a correct HTTP query string is
        appended to the URL without adding an extra slash
        """
        query = get_autoscale_links(
            '11111', group_id='1',
            query_params=[('marco', 'polo'),
                          ('ping', 'pong'),
                          ('razzle', 'dazzle')],
            format=None)
        self.assertEqual(
            query,
            '/v1.0/11111/groups/1/?marco=polo&ping=pong&razzle=dazzle')


class PaginationQueryArgGenerationTestCase(TestCase):
    """
    Tests for generating new pagination args in
    :func:`get_new_paginate_query_args`
    """
    def test_no_new_args_if_limited_data(self):
        """
        If the data is shorter then the limit, then there is probably no data
        after, hence no need for a next page, and so no query args are returned.
        """
        result = get_new_paginate_query_args(
            {'limit': 50, 'marker': 'meh'}, [{'id': str(i)} for i in range(5)])
        self.assertIsNone(result)

    def test_new_marker_if_too_much_data(self):
        """
        If the data length is equal to the limit, then there is
        probably another page of data, so a new marker is returned
        """
        result = get_new_paginate_query_args(
            {'limit': 5, 'marker': 'meh'}, [{'id': str(i)} for i in range(5)])
        self.assertEqual(result.get('marker'), '4')

    def test_respects_previous_limit(self):
        """
        New paginate query args has the same limit as the previous, but new
        marker
        """
        result = get_new_paginate_query_args(
            {'limit': 5, 'marker': 'meh'}, [{'id': str(i)} for i in range(5)])
        self.assertEqual(result.get('limit'), 5)

    def test_default_limit_if_no_previous_limit(self):
        """
        New paginate query args uses default limits if no old limits provided
        """
        self.addCleanup(set_config_data, {})
        set_config_data({'limits': {'pagination': 3}})

        result = get_new_paginate_query_args(
            {}, [{'id': str(i)} for i in range(3)])
        self.assertEqual(result.get('limit'), 3)


class RouteTests(RequestTestMixin, TestCase):
    """
    Test app.route.
    """
    def test_non_strict_slashes(self):
        """
        app.route should use strict_slahes=False which means that for a given
        route ending in a '/' the non-'/' version will result in a the handler
        being invoked directly instead of redirected.
        """
        requests = [0]

        class FakeApp(object):
            app = OtterApp()

            @app.route('/v1.0/foo/')
            @with_transaction_id()
            def foo(self, request, log):
                requests[0] += 1
                return 'ok'

        self.assert_status_code(200, method='GET', endpoint='/v1.0/foo',
                                root=FakeApp().app.resource())
        self.assertEqual(requests[0], 1)


class TransactionIdExtraction(RequestTestMixin, TestCase):
    """
    Test transaction_id extractor.
    """
    @mock.patch('otter.rest.decorators.generate_transaction_id')
    def test_extract_transaction_id(self, generate_transaction_id):
        """
        transaction_id should return a string transaction id when
        request has a transaction_id.
        """
        generate_transaction_id.return_value = 'transaction-id'

        transaction_ids = []

        class FakeApp(object):
            app = OtterApp()

            @app.route('/v1.0/foo')
            @with_transaction_id()
            def foo(self, request, log):
                transaction_ids.append(transaction_id(request))
                return 'ok'

        self.assert_status_code(200, method='GET', endpoint='/v1.0/foo',
                                root=FakeApp().app.resource())
        self.assertEqual(transaction_ids[0], 'transaction-id')


class DelegatedLogArgumentsTestCase(RequestTestMixin, TestCase):
    """
    Tests `log_arguments` decorator in conjunction with delegated routes.
    """

    def setUp(self):
        """
        Mock out the log in the `with_transaction_id` decorator.
        """
        self.mock_log = patch(self, 'otter.rest.decorators.log')

    def test_all_arguments_logged(self):
        """
        `log_arguments` should log all args, and kwargs on a route that
        has been delgated.
        """
        class FakeSubApp(object):
            app = OtterApp()

            def __init__(self, log):
                self.log = log

            @app.route('/<string:extra_arg1>/')
            @log_arguments
            def doWork(self, request, extra_arg1):
                return 'empty response'

        class FakeApp(object):
            app = OtterApp()

            @app.route('/', branch=True)
            @with_transaction_id()
            def delegate_to_dowork(self, request, log):
                return FakeSubApp(log).app.resource()

        self.assert_status_code(200, method='GET', endpoint='/some_data/',
                                root=FakeApp().app.resource())

        kwargs = {'extra_arg1': 'some_data'}
        self.mock_log.bind().bind().bind.assert_called_once_with(**kwargs)
