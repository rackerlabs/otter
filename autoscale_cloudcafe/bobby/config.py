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
    def group_id(self):
        """
        Group ID to be added to bobby
        """
        return self.get('group_id')

    @property
    def notification(self):
        """
        Notification for the tenant in bobby
        """
        return self.get('notification')

    @property
    def notification_plan(self):
        """
        Notification plan for the tenant in bobby
        """
        return self.get('notification_plan')
