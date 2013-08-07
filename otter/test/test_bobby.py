"""
Unit tests for the Bobby interface
"""

import mock
import json

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed

from otter import bobby


from otter.test.utils import patch
from otter.util.config import set_config_data


class BobbyTests(TestCase):
    """
    Bobby tests
    """
    def setUp(self):
        """
        set up test dependencies for Bobby.
        """

        fake_config = {
            'bobby_endpoint': 'url'
        }

        self.treq = patch(self, 'otter.bobby.treq')
        patch(self, 'otter.bobby.treq', new=self.treq)

        set_config_data(fake_config)

    def test_create_policy(self):
        """
        Test that we can create a policy in Bobby
        """
        response = mock.Mock()
        response.code = 201
        self.treq.post.return_value = succeed(response)

        content = mock.Mock()
        self.treq.json_content.return_value = succeed(content)

        d = bobby.create_policy('t1', 'g1', 'pol1', {'f': 'rrrr'}, 'ALARM DSL')

        result = self.successResultOf(d)
        self.assertEqual(result, content)

        self.treq.post.assert_called_once_with(
            'url/t1/groups/g1/policies',
            data=mock.ANY
        )

        data = self.treq.post.mock_calls[0][2]['data']

        self.assertEqual(json.loads(data),
                         {"checkTemplate": {"f": "rrrr"},
                          "alarmTemplate": "ALARM DSL",
                          "policyId": "pol1"})

        self.treq.json_content.assert_called_once_with(response)

    def test_create_server(self):
        """
        Test that we can create a server in Bobby
        """
        response = mock.Mock()
        response.code = 201
        self.treq.post.return_value = succeed(response)

        content = mock.Mock()
        self.treq.json_content.return_value = succeed(content)

        d = bobby.create_server('t1', 'g1',  'you_got_served', 'the_q_entity')

        result = self.successResultOf(d)
        self.assertEqual(result, content)

        self.treq.post.assert_called_once_with(
            'url/t1/groups/g1/servers',
            data=mock.ANY
        )

        data = self.treq.post.mock_calls[0][2]['data']

        self.assertEqual(json.loads(data),
                         {'entityId': 'the_q_entity',
                          'serverId': 'you_got_served'})

        self.treq.json_content.assert_called_once_with(response)

    def test_create_group(self):
        """
        Test that we can create a group in Bobby
        """
        response = mock.Mock()
        response.code = 201
        self.treq.post.return_value = succeed(response)

        content = mock.Mock()
        self.treq.json_content.return_value = succeed(content)

        d = bobby.create_group('t1', 'g1')

        result = self.successResultOf(d)
        self.assertEqual(result, content)

        self.treq.post.assert_called_once_with(
            'url/t1/groups',
            data=mock.ANY
        )

        data = self.treq.post.mock_calls[0][2]['data']

        self.assertEqual(json.loads(data),
                         {"notificationPlan": "Damnit, Bobby",
                          "notification": "Damnit, Bobby",
                          "groupId": "g1"})

        self.treq.json_content.assert_called_once_with(response)
