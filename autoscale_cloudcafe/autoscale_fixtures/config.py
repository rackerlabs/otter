"""
Define autoscale config values
"""
from cloudcafe.common.models.configuration import ConfigSectionInterface


class AutoscaleConfig(ConfigSectionInterface):
    """
    Defines the config values for autoscale
    """
    SECTION_NAME = 'autoscale'

    lc_image_ref = None
    lc_image_ref_alt = None

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
        return int(self.get('interval_time', 0))

    @property
    def timeout(self):
        """
        Timeout is the wait time for all servers on that group to be active
        """
        return int(self.get('timeout', 0))

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

    @property
    def load_balancer_endpoint_name(self):
        """
        load balancer endpoint name in the service catalog
        """
        return self.get('load_balancer_endpoint_name')

    @property
    def lbaas_region_override(self):
        """
        load balancer region in the service catalog
        """
        return self.get('lbaas_region_override', None)

    @property
    def server_region_override(self):
        """
        server region in the service catalog
        """
        return self.get('server_region_override', None)

    @property
    def non_autoscale_username(self):
        """
        Test username without autoscale endpoint in its service catalog
        """
        return self.get('non_autoscale_username')

    @property
    def non_autoscale_password(self):
        """
        Test password without autoscale endpoint in its service catalog
        """
        return self.get_raw('non_autoscale_password')

    @property
    def non_autoscale_tenant(self):
        """
        Test tenant without autoscale endpoint in its service catalog
        """
        return self.get('non_autoscale_tenant')

    @property
    def autoscale_na_la_aa(self):
        """
        Test username with admin access for next gen, load balancers and
        autoscale
        """
        return self.get('autoscale_na_la_aa')

    @property
    def autoscale_na_lo_aa(self):
        """
        Test username with admin access for next gen and autoscale &
        observer role for load balancer.
        """
        return self.get('autoscale_na_lo_aa')

    @property
    def autoscale_no_lo_aa(self):
        """
        Test username with observer access for next gen and load balancer &
        admin role for autoscale.
        """
        return self.get('autoscale_no_lo_aa')

    @property
    def autoscale_no_lo_ao(self):
        """
        Test username with observer access for next gen, load balancer &
        autoscale.
        """
        return self.get('autoscale_no_lo_ao')

    @property
    def autoscale_na_la_ao(self):
        """
        Test username with admin access for next gen, load balancer &
        observer role for autoscale.
        """
        return self.get('autoscale_na_la_ao')

    @property
    def autoscale_nc_lc_aa(self):
        """
        Test username with creator access for next gen, load balancer &
        admin role for autoscale.
        """
        return self.get('autoscale_nc_lc_aa')

    @property
    def autoscale_nc_lc_ao(self):
        """
        Test username with creator access for next gen, load balancer &
        observer role for autoscale.
        """
        return self.get('autoscale_nc_lc_ao')

    @property
    def autoscale_na_la_ano(self):
        """
        Test username with admin access for next gen, load balancer &
        no access for autoscale.
        """
        return self.get('autoscale_na_la_ano')

    @property
    def autoscale_nno_lno_ao(self):
        """
        Test username with admin access for next gen, load balancer &
        no access for autoscale.
        """
        return self.get('autoscale_nno_lno_ao')

    @property
    def autoscale_nno_lno_aa(self):
        """
        Test username with admin access for next gen, load balancer &
        no access for autoscale.
        """
        return self.get('autoscale_nno_lno_aa')

    @property
    def rcv3_endpoint_name(self):
        """
        Get the catalog name of the RCV3 endpoint
        """
        return self.get('rcv3_endpoint_name')

    @property
    def rcv3_load_balancer_pool(self):
        """
        Name and id of the shared RCV3 LB
        """
        temp = self.get('rcv3_load_balancer_pool')
        return temp

    @property
    def rcv3_region_override(self):
        """
        Allow override of the rcv3 region from the config file
        """
        return self.get('rcv3_region_override')

    @property
    def rcv3_cloud_network(self):
        """
        Specify the cloud network to use with RackConnect
        """
        return self.get('rcv3_cloud_network')

    @property
    def environment(self):
        """
        Read the environment for the config.  For example, dev, ci, etc.
        Default is production.
        """
        return self.get('environment', 'production')

    @property
    def mimic(self):
        """
        Specify whether this configuration is against a mimic instance.
        """
        return self.get('mimic', 'false').lower() == 'true'
