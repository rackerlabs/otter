"""
Tests for `worker.validate_config.py`
"""

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.test.utils import mock_log, patch, mock_treq, CheckFailure
from otter.util.config import set_config_data

from otter.worker.validate_config import (
    validate_launch_server_config, validate_image, validate_flavor, get_service_endpoint,
    InvalidLaunchConfiguration, UnknownImage, InactiveImage, UnknownFlavor)


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
                'imageRef': 'imagegood',
                'flavorRef': 'flavoreor'
            }
        }
        self.func_suffixes = ['image', 'flavor']
        self.properties = ['imageRef', 'flavorRef']
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
        Invalid image causes InvalidLaunchConfiguration
        """
        self.validate_image.return_value = defer.fail(UnknownImage('meh'))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, InvalidLaunchConfiguration)
        self.assertEqual(f.value.message, ('Following problems with launch configuration:\n' +
                                           'Invalid imageRef "meh" in launchConfiguration'))

    def test_inactive_image(self):
        """
        Image that is not in 'ACTIVE' state causes InvalidLaunchConfiguration
        """
        self.validate_image.return_value = defer.fail(InactiveImage('meh'))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, InvalidLaunchConfiguration)
        self.assertEqual(f.value.message, ('Following problems with launch configuration:\n' +
                                           'Inactive imageRef "meh" in launchConfiguration'))

    def test_invalid_flavor(self):
        """
        Invalid flavor causes InvalidLaunchConfiguration
        """
        self.validate_flavor.return_value = defer.fail(InvalidLaunchConfiguration(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, InvalidLaunchConfiguration)
        self.assertEqual(f.value.message, 'Following problems with launch configuration:\n:(')

    def test_invalid_image_and_flavor(self):
        """
        InvalidLaunchConfiguration is raised if both image and flavor are invalid
        """
        self.validate_image.return_value = defer.fail(InvalidLaunchConfiguration('image problem'))
        self.validate_flavor.return_value = defer.fail(InvalidLaunchConfiguration('flavor problem'))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, InvalidLaunchConfiguration)
        self.assertEqual(
            f.value.message,
            'Following problems with launch configuration:\nimage problem\nflavor problem')

    def test_other_error_raised(self):
        """
        `InvalidLaunchConfiguration` is raised even if any of the internal validate_* functions
        raise some other error
        """
        self.validate_image.return_value = defer.fail(ValueError(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        f = self.failureResultOf(d, InvalidLaunchConfiguration)
        self.assertEqual(f.value.message,
                         ('Following problems with launch configuration:\n'
                          'Invalid imageRef "imagegood" in launchConfiguration'))

    def test_validation_error_logged(self):
        """
        `InvalidLaunchConfiguration` is logged as msg
        """
        self.validate_image.return_value = defer.fail(InvalidLaunchConfiguration(':('))
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        self.failureResultOf(d, InvalidLaunchConfiguration)
        self.log.msg.assert_called_once_with(
            'Invalid imageRef "imagegood" in launchConfiguration',
            reason=CheckFailure(InvalidLaunchConfiguration))

    def test_optional_property(self):
        """
        If any of the optional properties is not available, it does not validate
        those and continues validating others
        """
        # Note: flavorRef is actually mandatory. It is used only for testing purpose
        del self.launch_config['server']['flavorRef']
        d = validate_launch_server_config(self.log, 'dfw', 'catalog', 'token', self.launch_config)
        self.successResultOf(d)
        self.assertFalse(self.validate_flavor.called)


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
        `InactiveImage` is raised if given image is inactive
        """
        self.treq.json_content.return_value = defer.succeed({'image': {'status': 'INACTIVE'}})
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        self.failureResultOf(d, InactiveImage)

    def test_unknown_image(self):
        """
        `UnknownImage` is raised if imageRef is unknown
        """
        self.treq.get.return_value = defer.succeed(mock.Mock(code=404))
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        self.failureResultOf(d, UnknownImage)

    def test_unexpected_http_status(self):
        """
        Errbacks if unexpected HTTP status is returned
        """
        self.treq.get.return_value = defer.succeed(mock.Mock(code=500))
        d = validate_image(self.log, 'token', 'endpoint', 'image_ref')
        self.failureResultOf(d)


class ValidateFlavorTests(TestCase):
    """
    Tests for `validate_flavor`
    """

    def setUp(self):
        """
        Mock treq
        """
        self.log = mock_log()
        self.treq = patch(self, 'otter.worker.validate_config.treq',
                          new=mock_treq(code=200, method='get'))
        patch(self, 'otter.util.http.treq', new=self.treq)
        self.headers = {'content-type': ['application/json'],
                        'accept': ['application/json']}

    def test_valid(self):
        """
        Succeeds if given flavor is valid
        """
        self.headers['x-auth-token'] = ['token']
        d = validate_flavor(self.log, 'token', 'endpoint', 'flavornum')
        self.successResultOf(d)
        self.treq.get.assert_called_once_with('endpoint/flavors/flavornum', headers=self.headers)

    def test_unknown_flavor(self):
        """
        UnknownFlavor is raised if flavor is unknown
        """
        self.treq.get.return_value = defer.succeed(mock.Mock(code=404))
        d = validate_flavor(self.log, 'token', 'endpoint', 'flavornum')
        self.failureResultOf(d, UnknownFlavor)

    def test_unexpected_http_status(self):
        """
        Errbacks if unexpected HTTP status is returned
        """
        self.treq.get.return_value = defer.succeed(mock.Mock(code=500))
        d = validate_flavor(self.log, 'token', 'endpoint', 'flavor_some')
        self.failureResultOf(d)


class GetServiceEndpointTests(TestCase):
    """
    Tests for `get_service_endpoint`
    """

    def setUp(self):
        """
        Mock public_endpoint_url and set_config_data
        """
        set_config_data({'cloudServersOpenStack': 'cloud'})
        self.public_endpoint_url = patch(self, 'otter.worker.validate_config.public_endpoint_url',
                                         return_value='http://service')

    def tearDown(self):
        """
        Reset config data
        """
        set_config_data({})

    def test_works(self):
        """
        Calls `public_endpoint_url` with correct args
        """
        endpoint = get_service_endpoint('catalog', 'dfw')
        self.assertEqual(endpoint, 'http://service')
        self.public_endpoint_url.assert_called_once_with('catalog', 'cloud', 'dfw')
