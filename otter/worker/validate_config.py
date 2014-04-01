"""
Contains code to validate launch config
"""

from twisted.internet import defer
import base64
import re
import itertools

from otter.util import logging_treq as treq

from otter.worker.launch_server_v1 import public_endpoint_url
from otter.util.config import config_value
from otter.util.http import (append_segments, headers, check_success,
                             raise_error_on_code, wrap_request_error)


b64_chars_re = re.compile("^[+/=a-zA-Z0-9]+$")


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


class InvalidPersonality(InvalidLaunchConfiguration):
    """
    Personality is invalid either because content is not base64 encoded or some other
    reason
    """
    def __init__(self, msg):
        super(InvalidPersonality, self).__init__(
            msg or 'Invalid personality in launch configuration')


class InvalidBase64Encoding(InvalidPersonality):
    """
    Personality has invalid base64 encoding in contents
    """
    def __init__(self, path):
        super(InvalidBase64Encoding, self).__init__(
            'Invalid base64 encoding for contents of path "{}"'.format(path))
        self.path = path


class InvalidMaxPersonality(InvalidPersonality):
    """
    Personality has more than maximum number of files allowed
    """
    def __init__(self, max_personality, length):
        super(InvalidMaxPersonality, self).__init__(
            'Number of files "{}" in personality exceeds maximum limit "{}"'.format(
                length, max_personality))
        self.max_personality = max_personality
        self.personality_length = length


class InvalidFileContentSize(InvalidPersonality):
    """
    Personality has file content whose size exceeds maximum limit allowed
    """
    def __init__(self, path, max_size):
        super(InvalidFileContentSize, self).__init__(
            'File "{}" content\'s size exceeds maximum size "{}"'.format(path, max_size))
        self.path = path
        self.max_size = max_size


def get_service_endpoint(service_catalog, region):
    """
    Get the service endpoint used to connect cloud services
    """
    cloudServersOpenStack = config_value('cloudServersOpenStack')
    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)
    return server_endpoint


def shorten(s, length):
    """
    Shorten `s` to `length` by appending it with "...". If `s` is small,
    return the same string

    >>> shorten("very long string", 9)
    "very l..."
    >>> shorten("small", 10)
    "small"
    """

    if len(s) > length:
        return s[:length - 3] + '...'
    else:
        return s


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
        (validate_personality, 'personality')
    ]

    def collect_errors(results):
        failures = [result for succeeded, result in results if not succeeded]
        if not failures:
            return None
        msg = ('Following problems with launch configuration:\n' +
               '\n'.join([failure.value.message for failure in failures]))
        raise InvalidLaunchConfiguration(msg)

    def raise_validation_error(failure, prop_name, prop_value):
        msg = 'Invalid {prop_name} "{prop_value}" in launchConfiguration'
        prop_value = shorten(str(prop_value), 128)
        log.msg(msg, prop_name=prop_name, prop_value=prop_value, reason=failure)
        if failure.check(InvalidLaunchConfiguration):
            return failure
        else:
            raise InvalidLaunchConfiguration(msg.format(prop_name=prop_name,
                                                        prop_value=prop_value))

    service_endpoint = get_service_endpoint(service_catalog, region)
    deferreds = []
    for validate, prop_name in validate_functions:
        prop_value = server.get(prop_name)
        if prop_value:
            d = validate(log, auth_token, service_endpoint, prop_value)
            d.addErrback(raise_validation_error, prop_name, prop_value)
            deferreds.append(d)

    return defer.DeferredList(deferreds, consumeErrors=True).addCallback(collect_errors)


def validate_image(log, auth_token, server_endpoint, image_ref):
    """
    Validate Image by getting the image information. It ensures that image is active
    """
    url = append_segments(server_endpoint, 'images', image_ref)
    d = treq.get(url, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(raise_error_on_code, 404, UnknownImage(image_ref), url,
                 'get_image')

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
    d = treq.get(url, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(raise_error_on_code, 404, UnknownFlavor(flavor_ref), url,
                 'get_flavor')

    # Extracting the content to avoid a strange bug in twisted/treq where next
    # subsequent call to nova hangs indefintely
    d.addCallback(treq.content)
    return d


def validate_personality(log, auth_token, server_endpoint, personality):
    """
    Validate personality by checking base64 encoded content and possibly limits
    """
    # Get limits
    url = append_segments(server_endpoint, 'limits')
    d = treq.get(url, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(wrap_request_error, url, 'get_limits')

    # Do not invalidate if we don't get limits
    d.addErrback(
        lambda f: log.msg('Skipping personality size checks due to limits error', reason=f))

    # Be optimistic and check base64 encoding anyways
    encoded_contents = []
    for _file in personality:
        try:
            if not b64_chars_re.match(_file['contents']):
                raise TypeError
            encoded_contents.append(base64.standard_b64decode(str(_file['contents'])))
        except TypeError:
            d.cancel()
            return defer.fail(InvalidBase64Encoding(_file['path']))

    def check_sizes(limits):

        # check max personality
        max_personality = limits['limits']['absolute']['maxPersonality']
        if len(personality) > max_personality:
            raise InvalidMaxPersonality(max_personality, len(personality))

        # check max content size
        max_file_size = limits['limits']['absolute']['maxPersonalitySize']
        for file, encoded_content in itertools.izip(personality, encoded_contents):
            if len(encoded_content) > max_file_size:
                raise InvalidFileContentSize(file['path'], max_file_size)

    d.addCallback(treq.json_content)
    d.addCallback(check_sizes)

    return d
