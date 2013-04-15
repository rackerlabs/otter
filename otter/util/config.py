"""
Implement a global configuration API.
"""
_config_data = None


def set_config_data(data):
    """
    Set the global configuration data.

    :param dict data: The configuration data, probably loaded from some JSON.
    """
    global _config_data
    _config_data = data


def config_value(name):
    """
    :param str name: Name is a . separated path to a configuration value
        stored in a nested dictionary.

    :returns: The value specificed in the configuration file, or None.
    """
    config = _config_data
    value = None
    parts = name.split('.')

    while parts:
        part = parts.pop(0)
        value = config.get(part)

        if isinstance(value, dict) and parts:
                config = value
                value = None

    return value
