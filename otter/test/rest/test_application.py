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
            },
            {
                'rel': 'bookmark',
                'href': '/' + url.split('/', 2)[-1]
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
