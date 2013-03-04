# encoding: utf-8

"""
Tests for :mod:`otter.rest.application`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.rest.application import get_autoscale_links


class LinkGenerationTestCase(TestCase):
    """
    Tests for generating autoscale links
    """

    def setUp(self):
        """
        Set a blank root URL
        """
        self.base_url_patcher = mock.patch(
            "otter.rest.application.get_url_root", return_value="")
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
        blank, then the returned base link is /v<api>/<tenant>/groups
        """
        self.assertEqual(
            get_autoscale_links('11111', api_version='3', format=None),
            '/v3/11111/groups')

        expected_url = '/v1.0/11111/groups'
        # test default API
        self.assertEqual(get_autoscale_links('11111', format=None),
                         expected_url)
        # test JSON formatting
        self.assertEqual(get_autoscale_links('11111'),
                         self._expected_json(expected_url))

    def test_get_only_groups_link_for_varying_other_args(self):
        """
        So long as the group ID is not a valid number, we still get the groups
        link /v<api>/<tenant>/groups
        """
        equivalents = [
            get_autoscale_links('11111', group_id='', format=None),
            get_autoscale_links('11111', policy_id='5', format=None),
            get_autoscale_links('11111', policy_id='', format=None)
        ]
        for equivalent in equivalents:
            self.assertEqual(equivalent, '/v1.0/11111/groups')

    def test_get_tenant_id_and_group_id(self):
        """
        If only the tenant ID and group ID are passed, and the rest of the
        arguments are blank, then the returned base link is
        /v<api>/<tenant>/groups/<group>
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', api_version='3',
                                format=None),
            '/v3/11111/groups/1')

        expected_url = '/v1.0/11111/groups/1'
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
            self.assertEqual(equivalent, '/v1.0/11111/groups/1')

    def test_get_tenant_id_and_group_id_and_blank_policy_id(self):
        """
        If the tenant ID, the group ID, and an empty policy ID (not None) are
        passed, the returned based link is
        /v<api>/<tenant>/groups/<group>/policies
        """
        self.assertEqual(
            get_autoscale_links('11111', group_id='1', policy_id="",
                                api_version='3', format=None),
            '/v3/11111/groups/1/policies')

        expected_url = '/v1.0/11111/groups/1/policies'
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
            '/v3/11111/groups/1/policies/5')

        expected_url = '/v1.0/11111/groups/1/policies/5'
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
            '/v3/11111/groups/1/policies/2/webhooks')

        expected_url = '/v1.0/11111/groups/1/policies/2/webhooks'
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
            '/v3/11111/groups/1/policies/2/webhooks/3')

        expected_url = '/v1.0/11111/groups/1/policies/2/webhooks/3'
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
            '/v1.0/11111/groups/1',
            '/v1.0/11111/groups/1/policies/2',
            '/v1.0/11111/groups/1/policies/2/webhooks/3'
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
            self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/1/xxx'},
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
        self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/1/xxx'},
                      json_blob)

        json_blob = get_autoscale_links(
            '11111', group_id='1', policy_id='2', webhook_id='3',
            capability_hash='xxx', capability_version="8")
        self.assertIn({'rel': 'capability', 'href': '/v1.0/execute/8/xxx'},
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
        self.assertEqual(snowman, '/v1.0/%E2%98%83/groups/%E2%98%83')
        self.assertTrue(isinstance(snowman, str))
