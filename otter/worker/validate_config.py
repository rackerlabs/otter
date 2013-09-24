"""
Contains code to validate launch config
"""

from twisted.internet import defer
import treq

from otter.worker.launch_server_v1 import public_endpoint_url
from otter.util.config import config_value
from otter.util.http import (append_segments, headers, check_success,
                             RequestError, APIError)


class InvalidLaunchConfiguration(Exception):
    """
    Represents an invalid launch configuration
    """
    pass


class UnknownImage(InvalidLaunchConfiguration):
    """
    Unknown imageRef in launch configuration
    """
    def __init__(self, image_ref):
        super(UnknownImage, self).__init__(
            'Invalid imageRef "{}" in launchConfiguration'.format(image_ref))
        self.image_ref = image_ref


class InactiveImage(InvalidLaunchConfiguration):
    """
    imageRef status is not active
    """
    def __init__(self, image_ref):
        super(InactiveImage, self).__init__(
            'Inactive imageRef "{}" in launchConfiguration'.format(image_ref))
        self.image_ref = image_ref


class UnknownFlavor(InvalidLaunchConfiguration):
    """
    Unknown flavorRef in launch configuration
    """
    def __init__(self, flavor_ref):
        super(UnknownFlavor, self).__init__(
            'Invalid flavorRef "{}" in launchConfiguration'.format(flavor_ref))
        self.flavor_ref = flavor_ref


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
        (validate_flavor, 'flavorRef')
    ]

    def collect_errors(results):
        failures = [result for succeeded, result in results if not succeeded]
        if not failures:
            return None
        msg = ('Following problems with launch configuration:\n' +
               '\n'.join([failure.value.message for failure in failures]))
        raise InvalidLaunchConfiguration(msg)

    def raise_validation_error(failure, prop_name, prop_value):
        msg = 'Invalid {} "{}" in launchConfiguration'.format(prop_name, prop_value)
        log.msg(msg, reason=failure)
        if failure.check(InvalidLaunchConfiguration):
            return failure
        else:
            raise InvalidLaunchConfiguration(msg)

    service_endpoint = get_service_endpoint(service_catalog, region)
    deferreds = []
    for validate, prop_name in validate_functions:
        prop_value = server.get(prop_name)
        if prop_value:
            d = validate(log, auth_token, service_endpoint, prop_value)
            d.addErrback(raise_validation_error, prop_name, prop_value)
            deferreds.append(d)

    return defer.DeferredList(deferreds, consumeErrors=True).addCallback(collect_errors)


def raise_error(failure, code, error, url, data=None):
    """
    Raise `error` if given `code` in APIError.code inside failure matches.
    Otherwise `RequestError` is raised with `url` and `data`
    """
    failure.trap(APIError)
    if failure.value.code == code:
        raise error
    raise RequestError(failure, url, data)


def validate_image(log, auth_token, server_endpoint, image_ref):
    """
    Validate Image by getting the image information. It ensures that image is active
    """
    url = append_segments(server_endpoint, 'images', image_ref)
    d = treq.get(url, headers=headers(auth_token))
    d.addCallback(check_success, [200, 203])
    d.addErrback(raise_error, 404, UnknownImage(image_ref), url, 'get_image')

    def is_image_active(image_detail):
        if image_detail['image']['status'] != 'ACTIVE':
            raise InactiveImage(image_ref)

    d.addCallback(treq.json_content)
    return d.addCallback(is_image_active)


def validate_flavor(log, auth_token, server_endpoint, flavor_ref):
    """
    Validate flavor by getting its information
    """
    url = append_segments(server_endpoint, 'flavors', flavor_ref)
    d = treq.get(url, headers=headers(auth_token))
    d.addCallback(check_success, [200, 203])
    d.addErrback(raise_error, 404, UnknownFlavor(flavor_ref), url, 'get_flavor')

    # Extracting the content to avoid a strange bug in twisted/treq where next
    # subsequent call to nova hangs indefintely
    d.addCallback(treq.content)
    return d
