"""
Define autoscale config values
"""
from cloudcafe.common.models.configuration import ConfigSectionInterface


class AutoscaleConfig(ConfigSectionInterface):
    """
    Defines the config values for autoscale
    """
    SECTION_NAME = 'autoscale'

    @property
    def tenant_id(self):
        """
        Tenant ID of the account
        """
        return self.get('tenant_id')

    @property
    def region(self):
        """
        Region to autoscale
        """
        return self.get('region')

    @property
    def gc_name(self):
        """
        group configuration name
        """
        return self.get('gc_name')

    @property
    def gc_cooldown(self):
        """
        group configuration cooldown time
        """
        return self.get('gc_cooldown')

    @property
    def gc_min_entities(self):
        """
        group configuration minimum entities
        """
        return self.get('gc_min_entities')

    @property
    def gc_max_entities(self):
        """
        group configuration maximum entities
        """
        return self.get('gc_max_entities')

    @property
    def gc_min_entities_alt(self):
        """
        group configuration alternate minimum entities
        """
        return self.get('gc_min_entities_alt')

    @property
    def lc_name(self):
        """
        launch configuration server name
        """
        return self.get('lc_name')

    @property
    def lc_flavor_ref(self):
        """
        launch configuration server flavor
        """
        return self.get('lc_flavor_ref')

    @property
    def lc_image_ref(self):
        """
        launch configuration server image id
        """
        return self.get('lc_image_ref')

    @property
    def lc_image_ref_alt(self):
        """
        Alternate launch configuration server image id
        """
        return self.get('lc_image_ref_alt')

    @property
    def sp_name(self):
        """
        scaling policy name
        """
        return self.get('sp_name')

    @property
    def sp_cooldown(self):
        """
        scaling policy cooldown time
        """
        return self.get('sp_cooldown')

    @property
    def sp_change(self):
        """
        scaling policy change in servers
        """
        return self.get('sp_change')

    @property
    def sp_policy_type(self):
        """
        scaling policy type
        """
        return self.get('sp_policy_type')

    @property
    def upd_sp_change(self):
        """
        scaling policy's update to change in servers
        """
        return self.get('upd_sp_change')

    @property
    def sp_change_percent(self):
        """
        scaling policy percent change in servers
        """
        return self.get('sp_change_percent')

    @property
    def sp_desired_capacity(self):
        """
        scaling policy's servers required to be in steady state
        """
        return self.get('sp_desired_capacity')

    @property
    def lc_load_balancers(self):
        """
        launch configuration for load balancers
        """
        return self.get('lc_load_balancers')

    @property
    def sp_list(self):
        """
        list of scaling policies
        """
        return self.get('sp_list')

    @property
    def wb_name(self):
        """
        Webhook name
        """
        return self.get('wb_name')

    @property
    def interval_time(self):
        """
        Interval time for polling group state table for active servers
        """
        return self.get('interval_time')

    @property
    def timeout(self):
        """
        Timeout is the wait time for all servers on that group to be active
        """
        return self.get('timeout')

    @property
    def autoscale_endpoint_name(self):
        """
        Autoscale endpoint name in the service catalog
        """
        return self.get('autoscale_endpoint_name')

    @property
    def server_endpoint_name(self):
        """
        server endpoint name in the service catalog
        """
        return self.get('server_endpoint_name')

    @property
    def server_endpoint(self):
        """
        server endpoint is the url to the otter application
        """
        return self.get('server_endpoint')
