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
from otter.util.http import (get_autoscale_links, transaction_id, get_collection_links,
                             get_groups_links, get_policies_links, get_webhooks_links)


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


class CollectionLinksTests(TestCase):
    """
    Tests for `get_collection_links`
    """

    def setUp(self):
        """
        Setup sample collection
        """
        self.coll = [{'id': '23'}, {'id': '567'}, {'id': '3444'}]

    def test_small_collection(self):
        """
        Collection len < limit gives self link only. No next link
        """
        links = get_collection_links(self.coll, 'url', 'self', limit=20)
        self.assertEqual(links, [{'href': 'url', 'rel': 'self'}])

    def test_limit_collection(self):
        """
        Collection len == limit gives next link also
        """
        links = get_collection_links(self.coll, 'url', 'self', limit=3)
        # FIXME: Cannot predict the sequence of marker and limit in URL
        self.assertEqual(links, [{'href': 'url', 'rel': 'self'},
                                 {'href': 'url?marker=3444&limit=3', 'rel': 'next'}])

    def test_big_collection(self):
        """
        Collection len > limit gives next link with marker based on limit
        """
        links = get_collection_links(self.coll, 'url', 'self', limit=2)
        # FIXME: Cannot predict the sequence of marker and limit in URL
        self.assertEqual(links, [{'href': 'url', 'rel': 'self'},
                                 {'href': 'url?marker=567&limit=2', 'rel': 'next'}])

    @mock.patch('otter.util.http.config_value', return_value=3)
    def test_no_limit(self, config_value):
        """
        Defaults to config limit if not given
        """
        links = get_collection_links(self.coll, 'url', 'self')
        self.assertEqual(links, [{'href': 'url', 'rel': 'self'},
                                 {'href': 'url?marker=3444&limit=3', 'rel': 'next'}])
        config_value.assert_called_once_with('limits.pagination')

    def test_rel_None(self):
        """
        Does not include self link if rel is None
        """
        links = get_collection_links(self.coll, 'url', None, limit=30)
        self.assertEqual(links, [])


class GetSpecificCollectionsLinks(TestCase):
    """
    Test for `get_groups_links`
    """

    def setUp(self):
        """
        Mock get_autoscale_links and get_collection_links
        """
        self.gal = patch(self, 'otter.util.http.get_autoscale_links', return_value='url')
        self.gcl = patch(self, 'otter.util.http.get_collection_links', return_value='col links')

    def test_get_groups_links(self):
        """
        `get_groups_links` gets link from `get_autoscale_links` and delegates to
        get_collection_links
        """
        links = get_groups_links('groups', 'tid', rel='rel', limit=2, marker='3')
        self.assertEqual(links, 'col links')
        self.gal.assert_called_once_with('tid', format=None)
        self.gcl.assert_called_once_with('groups', 'url', 'rel', 2, '3')

    def test_get_policies_links(self):
        """
        `get_policies_links` gets link from `get_autoscale_links` and delegates to
        get_collection_links
        """
        links = get_policies_links('policies', 'tid', 'gid', rel='rel', limit=2, marker='3')
        self.assertEqual(links, 'col links')
        self.gal.assert_called_once_with('tid', 'gid', '', format=None)
        self.gcl.assert_called_once_with('policies', 'url', 'rel', 2, '3')

    def test_get_webhooks_links(self):
        """
        `get_webhooks_links` gets link from `get_autoscale_links` and delegates to
        get_collection_links
        """
        links = get_webhooks_links('webhooks', 'tid', 'gid', 'pid', rel='rel',
                                   limit=2, marker='3')
        self.assertEqual(links, 'col links')
        self.gal.assert_called_once_with('tid', 'gid', 'pid', '', format=None)
        self.gcl.assert_called_once_with('webhooks', 'url', 'rel', 2, '3')


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
            log = mock.Mock()

            @app.route('/v1.0/foo/')
            @with_transaction_id()
            def foo(self, request):
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
            log = mock.Mock()

            @app.route('/v1.0/foo')
            @with_transaction_id()
            def foo(self, request):
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
        self.mock_log = mock.MagicMock()

    def test_all_arguments_logged(self):
        """
        `log_arguments` should log all args, and kwargs on a route that
        has been delgated.
        """
        class FakeSubApp(object):
            app = OtterApp()
            log = self.mock_log

            @app.route('/<string:extra_arg1>/')
            @with_transaction_id()
            @log_arguments
            def doWork(self, request, extra_arg1):
                return 'empty response'

        class FakeApp(object):
            app = OtterApp()

            @app.route('/', branch=True)
            def delegate_to_dowork(self, request):
                return FakeSubApp().app.resource()

        self.assert_status_code(200, method='GET', endpoint='/some_data/',
                                root=FakeApp().app.resource())

        kwargs = {'extra_arg1': 'some_data'}
        self.mock_log.bind().bind.assert_called_with(**kwargs)
