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

    def create_bobby_group_given(self, group_id=None, notification=None,
                                 notification_plan=None):
        """
        Creates a bobby group with teh given values
        """
        group_id = group_id or rand_name('012345DIFF-78f3-4543-85bc1-')
        notification = notification or self.bobby_config.notification
        notification_plan = notification_plan or self.bobby_config.notification_plan
        bobby_group = self.bobby_client.create_group(
            group_id=group_id,
            notification=notification,
            notification_plan=notification_plan)
        return bobby_group.entity
