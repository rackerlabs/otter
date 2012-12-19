"""
Interface to be used by the scaling groups engine
"""

from zope.interface import Interface, Attribute


class NoSuchScalingGroupError(Exception):
    """
    Error to be raised when attempting operations on a scaling group that
    does not exist.
    """
    def __init__(self, tenant_id, group_id):
        super(NoSuchScalingGroupError, self).__init__(
            "No such scaling group {uuid!s} for tenant {tenant!s}".format(
                tenant=tenant_id, uuid=group_id))


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
    uuid = Attribute("UUID of the scaling group - immutable.")

    def view_manifest():
        """
        The manifest contains everything required to configure this scaling:
        the config, the launch config, and all the scaling policies.

        :return: a dictionary with 3 keys: ``config`` containing the
            group configuration dictionary, ``launch`` containing the launch
            configuration dictionary, and ``policies`` containing a list of all
            the scaling policies
        :rtype: ``dict``
        """
        pass

    def view_config():
        """
        :return: a view of the config, as specified by
            :data:`otter.json_schema.scaling_group.config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        pass

    def view_launch_config():
        """
        :return: a view of the launch config, as specified by
            :data:`otter.json_schema.scaling_group.launch_config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        pass

    def view_state():
        """
        The state of the scaling group consists of a list unique IDs of the
        current entities in the scaling group, the a list of the unique IDs
        of the pending entities in the scaling group, the desired steady state
        number of entities, and a boolean specifying whether scaling is
        currently paused.

        :return: a view of the state of the scaling group in the form::

            {
                'active': [
                    '7e8b8ef3-ea06-44d2-8418-4bff11acc9fe',
                    '18aefdc0-abfd-4b40-a800-201f326fabe3'
                ],
                'pending': ['ccc26371-79dc-4839-b0ec-e6c3f31f415d'],
                'steadyState': 3,
                'paused': false
            }

        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        pass

    def update_config(config):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``config``.  This can update the already-existing values,
        or just overwrite them - it is up to the implementation.

        :param config: Configuration data in JSON format, as specified by
            :data:`otter.json_schema.scaling_group.config`
        :type config: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None
        """
        pass

    def update_launch_config(launch_config):
        """
        Update the scaling group launch configuration parameters based on the
        attributes in ``launch_config``.  This can update the already-existing
        values, or just overwrite them - it is up to the implementation.

        :param launch_config: launch config data in JSON format, as specified
            by :data:`otter.json_schema.scaling_group.launch_config`
        :type launch_config: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None
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

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None
        """
        pass

    def bounce_entity(entity_id):
        """
        Rebuilds an entity given by the entity ID.  This essentially deletes
        the given entity and a new one will be rebuilt in its place.

        :param entity_id: the uuid of the entity to delete
        :type entity_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: NoSuchEntityError if the entity is not a member of the scaling
            group
        """
        pass


class IScalingGroupCollection(Interface):
    """
    Collection of scaling groups
    """
    def create_scaling_group(tenant_id, config, launch, policies=None):
        """
        Create scaling group based on the tenant id, the configuration
        paramaters, the launch config, and optional scaling policies.

        :param tenant_id: the tenant ID of the tenant the scaling group
            belongs to
        :type tenant_id: ``str``

        :param config: scaling group configuration options in JSON format, as
            specified by :data:`otter.json_schema.scaling_group.config`
        :type data: ``dict``

        :param launch: scaling group launch configuration options in JSON
            format, as specified by
            :data:`otter.json_schema.scaling_group.launch_config`
        :type data: ``dict``

        :param policies: list of scaling group policies, each one given as a
            JSON blob as specified by
            :data:`otter.json_schema.scaling_group.scaling_policy`
        :type data: ``list`` of ``dict``

        :return: uuid of the newly created scaling group
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with `str`
        """
        pass

    def delete_scaling_group(tenant_id, scaling_group_id):
        """
        Delete the scaling group

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :param scaling_group_id: the uuid of the scaling group to delete
        :type scaling_group_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if the scaling group id
            doesn't exist for this tenant id
        """
        pass

    def list_scaling_groups(tenant_id):
        """
        List the scaling groups for this tenant ID

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: a list of scaling groups
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            ``list`` of :class:`IScalingGroup` providers
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
        :rtype: :class:`IScalingGroup` provider (no
            :class:`twisted.internet.defer.Deferred`)
        """
        pass
