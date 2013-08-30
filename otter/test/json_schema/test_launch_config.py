"""
Tests for `json_schema.launch_config.py`
"""

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.test.utils import mock_log, patch

from otter.json_schema.launch_config import validate_launch_config
from otter.supervisor import set_supervisor


class ValidateLaunchConfigTests(TestCase):
    """
    Tests for `validate_launch_config`
    """

    def setUp(self):
        """
        Mock supervisor and other validate_* methods
        """
        self.log = mock_log()
        self.launch_config = {
            'server': {
                'imageRef': 'imagekdfj',
                'flavorRef': 'flavoreor',
                'keypair': 'key',
                'personality': 'perso'
            }
        }
        self.func_suffixes = ['image', 'flavor', 'key_pairs', 'personality']
        self.properties = ['imageRef', 'flavorRef', 'keypair', 'personality']
        for func_suffix in self.func_suffixes:
            setattr(self, 'validate_{}'.format(func_suffix), patch(
                self, 'otter.json_schema.launch_config.validate_{}'.format(func_suffix),
                return_value=defer.succeed(None)))
        self.supervisor = mock.MagicMock(spec=['auth_function'])
        set_supervisor(self.supervisor)
        self.get_service_endpoint = patch(
            self, 'otter.json_schema.launch_config.get_service_endpoint',
            return_value='service')

    def tearDown(self):
        """
        reset the supervisor
        """
        set_supervisor(None)

    def test_valid(self):
        """
        All good
        """
        self.supervisor.auth_function.return_value = defer.succeed(('token', 'catalog'))

        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        self.successResultOf(d)

        for suffix, prop in zip(self.func_suffixes, self.properties):
            func = getattr(self, 'validate_{}'.format(suffix))
            func.assert_called_once_with(self.log, 'token', 'service',
                                         self.launch_config['server'][prop])
