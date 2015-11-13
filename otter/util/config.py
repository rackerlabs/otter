"""
Implement a global configuration API.
"""
from toolz.dicttoolz import get_in, update_in

_config_data = {}


def set_config_data(data):
    """
    Set the global configuration data.

    :param dict data: The configuration data, probably loaded from some JSON.
    """
    global _config_data
    _config_data = data


def update_config_data(name, value):
    """
    Update config value to existing configuration

    :param str name: Name is a . separated path to a configuration value
        stored in a nested dictionary.
    :param value: Value to be updated
    """
    global _config_data
    _config_data = update_in(_config_data, name.split('.'), lambda _: value)


def config_value(name):
    """
    :param str name: Name is a . separated path to a configuration value
        stored in a nested dictionary.

    :returns: The value specificed in the configuration file, or None.
    """
    return get_in(name.split('.'), _config_data)
