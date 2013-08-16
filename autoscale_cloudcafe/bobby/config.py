"""
Define autoscale config values
"""
from cloudcafe.common.models.configuration import ConfigSectionInterface


class BobbyConfig(ConfigSectionInterface):
    """
    Defines the config values for bobby
    """
    SECTION_NAME = 'bobby'

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
        """
