"""
Test update bobby policy in bobby
"""
from test_repo.bobby.fixtures import BobbyFixture
from cloudcafe.common.tools.datagen import rand_name


class UpdateBobbyPolicyTest(BobbyFixture):

    """
    Tests for update group in bobby
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a bobby policy with the given values for given group id
        """
        super(UpdateBobbyPolicyTest, cls).setUpClass()
        cls.group_id = rand_name('TEST-GROUP-78f3-4543-85bc1')
        cls.policy_id = rand_name('TEST-POLICY-78f3-4543-85bc1')
        cls.alarm_template = '98789798'
        cls.check_template = '987897'
        cls.bobby_policy = cls.bobby_behaviors.create_bobby_policy_given(
            group_id=cls.group_id,
            policy_id=cls.policy_id,
            alarm_template=cls.alarm_template,
            check_template=cls.check_template)
        cls.upd_check_template = 'updated'  # change to dict later
        cls.upd_alarm_template = 'updated'  # change to dict later

    def test_update_bobby_policy_response(self):
        """
        update the bobby policy and verify the response code is 204.
        """
        update_response = self.bobby_client.update_bobby_policy(group_id=self.group_id,
                                                                policy_id=self.policy_id,
                                                                alarm_template=self.upd_check_template,
                                                                check_template=self.upd_alarm_template)
        self.assertEquals(update_response.status_code, 204,
                          msg='Update a bobby policy resulted in {0} as against '
                          ' 204'.format(update_response.status_code))
        self.validate_headers(update_response.headers)

    def test_update_non_existant_group(self):
        """
        update a non existant group and verify the response code is 404.
        """
        update_response = self.bobby_client.update_bobby_policy(
            'I-DONT-EXIST', self.policy_id, self.upd_check_template, self.upd_alarm_template)
        self.assertEquals(update_response.status_code, 404,
                          msg='updating a bobby policy resulted in {0} as against '
                          ' 404 for an invalid groupId'.format(update_response.status_code))
        self.validate_headers(update_response.headers)

    def test_update_non_existant_policy(self):
        """
        update a non existant policy and verify the response code is 404.
        """
        update_response = self.bobby_client.update_bobby_policy(
            self.group_id, 'I-DONT-EXIST', self.upd_check_template, self.upd_alarm_template)
        self.assertEquals(update_response.status_code, 404,
                          msg='updating a bobby policy resulted in {0} as against '
                          ' 404 for an invalid policyId'.format(update_response.status_code))
        self.validate_headers(update_response.headers)

    def test_update_policy_without_alarm_template(self):
        """
        update a bobby policy without alarm template and verify the response code is 403.
        """
        update_response = self.bobby_client.update_bobby_policy(group_id=self.group_id,
                                                                policy_id=self.policy_id,
                                                                alarm_template=None,
                                                                check_template=self.upd_alarm_template)
        self.assertEquals(update_response.status_code, 403,
                          msg='updating a bobby policy without alarm template resulted in'
                          ' {0} as against 403 '.format(update_response.status_code))
        self.validate_headers(update_response.headers)

    def test_update_policy_without_check_template(self):
        """
        update a bobby policy without check template and verify the response code is 403.
        """
        update_response = self.bobby_client.update_bobby_policy(group_id=self.group_id,
                                                                policy_id=self.policy_id,
                                                                check_template=None,
                                                                alarm_template=self.upd_alarm_template)
        self.assertEquals(update_response.status_code, 403,
                          msg='updating a bobby policy without check template resulted in'
                          ' {0} as against 403 '.format(update_response.status_code))
        self.validate_headers(update_response.headers)
