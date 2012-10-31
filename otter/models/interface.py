"""
Interface to be used by the scaling groups engine
"""

from zope.interface import Interface, Attribute


class NoSuchScalingGroupError(Exception):
    """
    Error to be raised when attempting operations on a scaling group that
    does not exist.
    """
    def __init__(self, tenant_id, scaling_group_id):
        super(NoSuchScalingGroupError, self).__init__(
            "Scaling group {0!r} does not exist for tenant {0!s}".format(
                scaling_group_id, tenant_id))


class NoSuchEntityError(Exception):
    """
    Error to be raised when attempting operations on an entity that does not
    exist.
    """
    pass


class InvalidEntityError(Exception):
    """
    Error to be raised when attempting to add an invalid entity (wrong
    permissions, or wrong entity type) to a scaling group.
    """
    pass


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group.")
    name = Attribute("Name of the scaling group.")

    entity_type = Attribute("What type of entity this scaling group scales.")
    region = Attribute("Region the scaling group covers.")

    cooldown = Attribute(
        "Cooldown period before more entities are added, given in seconds.")
    min_entities = Attribute(
        "Minimum number of entities in the scaling group.")
    max_entities = Attribute(
        "Maximum number of entities in the scaling group.")
    steady_state_entities = Attribute(
        "The desired steady state number of entities - defaults to the "
        "minimum. This number represents how many entities _should_ be "
        "currently in the system to handle the current load. Its value is "
        "constrained to be between min_entities and max_entities, inclusive.")
    metadata = Attribute("User-provided metadata")

    def view():
        """
        :return: a view of the config as dict, as specified by
            :data:`scaling_group_config_schema`
        :rtype: ``dict``
        """
        pass

    def update(data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data``.  This updates the already-existing values, rather than
        overwrites them.  (Enforce override-only updates should happen
        elsewhere.)

        ``uuid``, ``region``, and ``entity_type`` cannot be updated.

        :param data: Configuration data in JSON format, as specified by
            :data:`scaling_group_config_schema`
        :type data: ``dict``

        :return: None
        """
        pass

    def list():
        """
        :return: a list of the uuids of the entities in the scaling group
        :rtype: ``list`` of ``strings``
        """
        pass

    def delete(entity_id):
        """
        Deletes an entity given by the entity ID

        :param entity_id: the uuid of the entity to delete
        :type entity_id: ``str``

        :return: None

        :raises: NoSuchEntityError if the entity is not a member of the scaling
            group
        """
        pass

    def add(entity_id):
        """
        Adds the entity to the group manually, given the entity ID

        :param entity_id: the uuid of the entity to add
        :type entity_id: ``str``

        :return: None

        :raises: InvalidEntityError if the entity cannot be added due to
            permission errors, or if the entity is the wrong type
        :raises: NoSuchEntityError if the entity does not exist
        """
        pass


class IScalingGroupCollection(Interface):
    """
    Collection of scaling groups
    """
    def create_scaling_group(tenant_id, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data``.

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :param data: Configuration data in JSOn format, as specified by
            :data:`scaling_group_config_schema`
        :type data: ``dict``

        :return: uuid of the newly created scaling group
        :rtype: 'str'
        """
        pass

    def delete_scaling_group(tenant_id, scaling_group_id):
        """
        Delete the scaling group

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :param scaling_group_id: the uuid of the scaling group to delete
        :type scaling_group_id: ``str``

        :return: None

        :raises: :class`NoSuchScalingGroupError` if the scaling group id is
            invalid or doesn't exist for this tenant id
        """
        pass

    def list_scaling_groups(tenant_id):
        """
        List the scaling groups

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: mapping of scaling group uuid's to the scaling group's model
        :rtype: ``dict`` of ``str`` mapped to :class:`IScalingGroup` provider
        """
        pass

    def get_scaling_group(tenant_id, scaling_group_id):
        """
        Get a scaling group model

        Will return a scaling group even if the ID doesn't exist,
        but the scaling group will throw exceptions when you try to do things
        with it.

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: scaling group model object
        :rtype: :class:`IScalingGroup` provider

        :raises: :class`NoSuchScalingGroupError` if the scaling group id is
            invalid or doesn't exist for this tenant id
        """
        pass


# Schema (as per Internet Draft 3 of JSON Schema) for the configuration of a
# scaling group
scaling_group_config_schema = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "required": True,
        },
        "entity_type": {
            "type": "string",
            "enum": ["servers"],
            "required": True,
        },
        "region": {
            "type": "string",
            "enum": ["DFW", "ORD", "LON"],
            "required": True,
        },
        "cooldown": {
            "type": "number",
            "mininum": 0
        },
        "min_entities": {
            "type": "integer",
            "minimum": 0
        },
        "max_entities": {
            "type": "integer",
            "minimum": 0
        },
        "steady_state_entities": {
            "type": "integer",
            "minimum": 0
        },
        "metadata": {
            "type": "object"
        }
    }
}

for property_name in scaling_group_config_schema['properties']:
    scaling_group_config_schema['properties'][property_name]['title'] = (
        IScalingGroup[property_name].__doc__)

# the update schema does not have entity_type or region, since those cannot
# be updated
scaling_group_update_config_schema = dict(scaling_group_config_schema)
del scaling_group_update_config_schema['properties']['entity_type']
del scaling_group_update_config_schema['properties']['region']
