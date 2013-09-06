"""
Contains code to validate launch config

TODO: Apart from this, add schema validation to a minimum extent
"""

from twisted.internet import defer
import treq

from otter.worker.launch_server_v1 import public_endpoint_url
from otter.util.config import config_value
from otter.util.http import (append_segments, headers, check_success,
                             wrap_request_error)


class InvalidLaunchConfiguration(Exception):
    """
    Represents an invalid launch configuration
    """
    def __init__(self, message):
        super(Exception, self).__init__(message)
        self.message = message


def get_service_endpoint(service_catalog, region):
    """
    Get the service endpoint used to connect cloud services
    """
    cloudServersOpenStack = config_value('cloudServersOpenStack')
    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)
    return server_endpoint


def validate_launch_server_config(log, region, service_catalog, auth_token, launch_config):
    """
    Validate launch_server type configuration

    :returns: Deferred that is fired if configuration is valid and errback(ed) with
              `InvalidLaunchConfiguration` if invalid
    """

    server = launch_config['server']

    validate_functions = [
        (validate_image, 'imageRef'),
        (validate_flavor, 'flavorRef'),
        (validate_key_pairs, 'keypair'),
        (validate_personality, 'personality')
    ]

    def collect_errors(results):
        failures = [result for succeeded, result in results if not succeeded]
        if not failures:
            return None
        if len(failures) > 1:
            msg = ('Following problems with launch configuration:\n' +
                   '\n'.join([failure.value.message for failure in failures]))
            raise InvalidLaunchConfiguration(msg)
        else:
            return failures[0]

    def raise_validation_error(failure, prop):
        log.msg('Validation of "{}" property in launchConfiguration failed'.format(prop),
                reason=failure)
        if failure.check(InvalidLaunchConfiguration):
            return failure
        else:
            raise InvalidLaunchConfiguration('Invalid "{}" in launchConfiguration'.format(prop))

    service_endpoint = get_service_endpoint(service_catalog, region)
    deferreds = []
    for validate, prop in validate_functions:
        prop_value = server.get(prop)
        if prop_value:
            d = validate(log, auth_token, service_endpoint, prop_value)
            d.addErrback(raise_validation_error, prop)
            deferreds.append(d)

    return defer.DeferredList(deferreds, consumeErrors=True).addCallback(collect_errors)


def validate_image(log, auth_token, server_endpoint, image_ref):
    """
    Validate Image by getting the image information. It ensures that image is active
    """
    d = treq.get(append_segments(server_endpoint, 'images', image_ref),
                 headers=headers(auth_token))
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, server_endpoint, 'get_image')

    def is_image_active(image_detail):
        if image_detail['image']['status'] != 'ACTIVE':
            raise InvalidLaunchConfiguration('Image "{}" is not active'.format(image_ref))

    d.addCallback(treq.json_content)
    return d.addCallback(is_image_active)


def validate_flavor(log, auth_token, server_endpoint, flavor_ref):
    """
    Validate flavor by getting its information
    """
    d = treq.get(append_segments(server_endpoint, 'flavors', flavor_ref),
                 headers=headers(auth_token))
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, server_endpoint, 'get_flavor')
    return d


def validate_key_pairs(log, auth_token, server_endpoint, key_pairs):
    """
    Validate key pairs
    """
    # TODO
    return defer.suceed(True)


def validate_personality(log, auth_token, server_endpoint, personality):
    """
    Validate personality
    """
    # TODO
    return defer.suceed(True)
