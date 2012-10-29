"""
Interface to be used by the scaling groups engine
"""

from zope.interface import Interface, Attribute


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group")
    name = Attribute("Name of the scaling group")

    entity_type = Attribute("What type of entity this scaling group scales")
    region = Attribute("Region the scaling group covers")

    cooldown = Attribute(
        "Cooldown period before more entities are added, given in seconds")
    min_entities = Attribute("Minimum entities")
    max_entities = Attribute("Maxmimum entities")
    steady_state_entities = Attribute("Steady state entities")
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
        in ``data``

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
        """
        pass

    def add(entity_id):
        """
        Adds the entity to the group manually, given the entity ID

        :param entity_id: the uuid of the entity to add
        :type entity_id: ``str``

        :return: None
        """
        pass


class IScalingGroupCollection(Interface):
    """
    Collection of scaling groups
    """
    def create(tenant, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```
        """
        pass

    def delete(tenant, scaling_group_id):
        """
        Delete the scaling group
        """
        pass

    def list(tenant):
        """
        List the scaling groups
        """
        pass

    def get(tenant, scaling_group_id):
        """
        Get a scaling group

        Will return a scaling group even if the ID doesn't exist,
        but the scaling group will throw exceptions when you try to do things
        with it.
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
