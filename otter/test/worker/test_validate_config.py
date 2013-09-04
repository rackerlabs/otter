"""
Tests for `worker.validate_config.py`
"""

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from jsonschema import ValidationError

from otter.test.utils import mock_log, patch, mock_treq

from otter.worker.validate_config import validate_launch_server_config, validate_image


class ValidateLaunchServerConfigTests(TestCase):
    """
    Tests for `validate_launch_server_config`
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
                self, 'otter.worker.validate_config.validate_{}'.format(func_suffix),
                return_value=defer.succeed(None)))
        self.get_service_endpoint = patch(
            self, 'otter.worker.validate_config.get_service_endpoint',
            return_value='service')

    def test_valid(self):
        """
        `validate_launch_server_config` succeeds when all the validate_* are called and succeeds
        """
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
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
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, ':(')

    def test_invalid_flavor(self):
        """
        Invalid flavor causes ValidationError
        """
        self.validate_flavor.return_value = defer.fail(ValidationError(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, ':(')

    def test_invalid_image_and_flavor(self):
        """
        ValidationError is raised if both image and flavor are invalid
        """
        self.validate_image.return_value = defer.fail(ValidationError(':('))
        self.validate_flavor.return_value = defer.fail(ValidationError(":'("))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        self.failureResultOf(d, ValidationError)
        # It is not well defined (maybe I dont know) which validationerror
        # will be picked up. hence not checking value

    def test_other_error_raised(self):
        """
        `ValidationError` is raised even if any of the internal validate_* functions raise some
        other error
        """
        self.validate_image.return_value = defer.fail(ValueError(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, 'Invalid "imageRef" in launchConfiguration')

    def test_validation_error_logged(self):
        """
        `ValidationError` is logged as msg
        """
        self.validate_image.return_value = defer.fail(ValidationError(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
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
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        self.successResultOf(d)
        self.assertFalse(self.validate_personality.called)


class ValidateImageTests(TestCase):
    """
    Tests for `validate_image`
    """

    def setUp(self):
        """
        Mock treq
        """
        self.log = mock_log()
        self.treq = patch(self, 'otter.worker.validate_config.treq',
                          new=mock_treq(code=200,
                                        json_content={'image': {'status': 'ACTIVE'}},
                                        method='get'))
        patch(self, 'otter.util.http.treq', new=self.treq)
        self.headers = {'content-type': ['application/json'],
                        'accept': ['application/json']}

    def test_valid(self):
        """
        Succeeds if given image is valid
        """
        self.headers['x-auth-token'] = ['token']
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        self.successResultOf(d)
        self.treq.get.assert_called_with('endpoint/images/image_ref', headers=self.headers)

    def test_inactive_image(self):
        """
        `ValidationError` is raised if given image is inactive
        """
        self.treq.json_content.return_value = defer.succeed({'image': {'status': 'INACTIVE'}})
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        f = self.failureResultOf(d, ValidationError)
        self.assertEqual(f.value.message, 'Image "image_ref" is not active')

    def test_unknown_image(self):
        """
        Errbacks if imageRef is unknown
        """
        self.treq.get.return_value = defer.succeed(mock.MagicMock(code=404))
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        self.failureResultOf(d)
