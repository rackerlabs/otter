"""
Behaviors for Bobby
"""
from cafe.engine.behaviors import BaseBehavior
from cloudcafe.common.tools.datagen import rand_name


class BobbyBehaviors(BaseBehavior):

    """
    :summary: Behavior Module for the Bobby REST API
    :note: Should be the primary interface to a test case or external tool
    """

    def __init__(self, bobby_config, bobby_client):
        """
        Instantiate config and client
        """
        super(BobbyBehaviors, self).__init__()
        self.bobby_config = bobby_config
        self.bobby_client = bobby_client

    def create_bobby_group_min(self):
        """
        Creates a bobby group with the valus in the config
        """
        bobby_group = self.bobby_client.create_group(
            group=self.bobby_config.group_Id,
            notification=self.bobby_config.notification,
            notification_plan=self.bobby_config.notification_plan)
        return bobby_group.entity
