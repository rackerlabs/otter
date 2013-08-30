"""
Tests for `json_schema.launch_config.py`
"""

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from jsonschema import ValidationError

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
        self.supervisor.auth_function.return_value = defer.succeed(('token', 'catalog'))
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
        `validate_launch_config` succeeds when all the validate_* are called and succeeds
        """
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        self.successResultOf(d)

        for suffix, prop in zip(self.func_suffixes, self.properties):
            func = getattr(self, 'validate_{}'.format(suffix))
            func.assert_called_once_with(self.log, 'token', 'service',
                                         self.launch_config['server'][prop])

    def test_invalid_image(self):
        """
        Invalid image causes ValidationError
        """
        self.validate_image.return_value = defer.fail(ValidationError(':('))
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, ':(')

    def test_invalid_flavor(self):
        """
        Invalid flavor causes ValidationError
        """
        self.validate_flavor.return_value = defer.fail(ValidationError(':('))
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, ':(')

    def test_invalid_image_and_flavor(self):
        """
        ValidationError is raised if both image and flavor are invalid
        """
        self.validate_image.return_value = defer.fail(ValidationError(':('))
        self.validate_flavor.return_value = defer.fail(ValidationError(":'("))
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        self.failureResultOf(d, ValidationError)
        # It is not well defined (maybe I dont know) which validationerror
        # will be picked up. hence not checking value

    def test_other_error_raised(self):
        """
        `ValidationError` is raised even if any of the internal validate_* functions raise some
        other error
        """
        self.validate_image.return_value = defer.fail(ValueError(':('))
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, 'Invalid "imageRef" in launchConfiguration')

    def test_validation_error_logged(self):
        """
        `ValidationError` is logged as msg
        """
        self.validate_image.return_value = defer.fail(ValidationError(':('))
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.log.msg.assert_called_once_with(
            'Validation of "imageRef" property in launchConfiguration failed',
            reason=f)

    def test_no_personality(self):
        """
        If any of the optional properties like personality is not available, it does not validate
        those and continues validating others
        """
        del self.launch_config['server']['personality']
        d = validate_launch_config(self.log, 'tenant', self.launch_config)
        self.successResultOf(d)
        self.assertFalse(self.validate_personality.called)

    def test_auth_fails(self):
        """
        What to do if authentication fails?
        """
        # TODO
        pass
