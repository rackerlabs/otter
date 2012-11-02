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


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    # Immutable once the scaling group is created
    uuid = Attribute("UUID of the scaling group.")
    entity_type = Attribute("What type of entity this scaling group scales.")
    region = Attribute("Region the scaling group covers.")

    # State values
    def view_config():
        """
        :return: a view of the config, as specified by
            :data:`scaling_group_config_schema`
        :rtype: ``dict``
        """
        pass

    def view_state():
        """
        The state of the scaling group consists of the current number of
        entities in the scaling group and the desired steady state number of
        entities.

        :return: a view of the state of the scaling group as a dict
        """
        pass

    def update_config(config):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``config``.  This updates the already-existing values,
        rather than overwrites them.  (Enforce override-only updates should
        happen elsewhere.)

        :param config: Configuration data in JSON format, as specified by
            :data:`scaling_group_config_schema`
        :type config: ``dict``

        :return: None
        """
        pass

    def set_steady_state(steady_state):
        """
        The steady state represents the number of entities - defaults to the
        minimum. This number represents how many entities _should_ be
        currently in the system to handle the current load. Its value is
        constrained to be between ``min_entities`` and ``max_entities``,
        inclusive.

        :param steady_state: The new value for the desired number of entities
            in steady state.  If this value is greater than ``max_entities``,
            the value will be set to ``max_entities``.  Similarly, if this
            value is less than ``min_entities``, the value will be set to
            ``min_entities``.
        :type steady_state: ``int``
        """
        pass

    def list_entities():
        """
        :return: a list of the uuids of the entities in the scaling group
        :rtype: ``list`` of ``strings``
        """
        pass

    def bounce_entity(entity_id):
        """
        Rebuilds an entity given by the entity ID.  This essentially deletes
        the given entity and a new one will be rebuilt in its place.

        :param entity_id: the uuid of the entity to delete
        :type entity_id: ``str``

        :return: None

        :raises: NoSuchEntityError if the entity is not a member of the scaling
            group
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

        :raises: :class:`NoSuchScalingGroupError` if the scaling group id is
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

        :raises: :class:`NoSuchScalingGroupError` if the scaling group id is
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
            "default": "",
            "title": "Name of the scaling group."
        },
        "cooldown": {
            "type": "number",
            "mininum": 0,
            "title": ("Cooldown period before more entities are added, "
                      "given in seconds.")
        },
        "min_entities": {
            "type": "integer",
            "minimum": 0,
            "title": "Minimum number of entities in the scaling group."
        },
        "max_entities": {
            "type": ["integer", "null"],
            "minimum": 0,
            "default": None,
            "title": ("Maximum number of entities in the scaling group. "
                      "Defaults to null, meaning no maximum.")
        },
        "metadata": {
            "type": "object",
            "title": "User-provided metadata"
        }
    },
    "additionalProperties": False
}
