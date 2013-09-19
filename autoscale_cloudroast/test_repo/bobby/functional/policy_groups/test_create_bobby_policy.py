"""
Test to create and verify policy in bobby.
"""
from test_repo.bobby.fixtures import BobbyFixture
import unittest
from cloudcafe.common.tools.datagen import rand_name


class CreateBobbyPolicyTest(BobbyFixture):

    """
    Verify create policy in bobby.
    """

    def test_create_bobby_policy_response(self):
        """
        Create a policy in bobby, and verify the response code is 201,
        the headers and the response object.
        """
        group_id = rand_name('0123GROUP-78f3-4543-85bc1-')
        policy_id = rand_name('0123POLICY-78f3-4543-85bc1-')
        alarm_template = '8787978'
        check_template = '9987987'
        create_bobby_policy_response = self.bobby_behaviors.create_bobby_policy_given(
            group_id=group_id,
            policy_id=policy_id,
            alarm_template=alarm_template,
            check_template=check_template)
        self.assertEquals(create_bobby_policy_response.status_code, 201,
                          msg='The response code for create policy in bobby '
                          'resulted in {0}'.format(create_bobby_policy_response.status_code))
        self.validate_headers(create_bobby_policy_response.headers)
        bobby_policy = create_bobby_policy_response.entity
        self.assertEquals(bobby_policy.groupId, group_id,
                          msg='The groupId in the response does not match')
        self.assertEquals(bobby_policy.policyId, policy_id,
                          msg='The policyId in the response does not match')
        self.assertEquals(bobby_policy.alarmTemplate, alarm_template,
                          msg='The alarmTemplate in the response does not match')
        self.assertEquals(bobby_policy.checkTemplate, check_template,
                          msg='The checkTemplate in the response does not match')

    @unittest.skip('AUTO-571')
    def test_create_policies_with_same_policy_ids(self):
        """
        Create a policy in bobby with the same policy ID and groupId  and verify 403
        is returned when duplicated.
        """
        policy_id = 'POLICY-78f3-4543-85bc-e75a407c08d4'
        group_id = 'GROUP-78f3-4543-85bc-e75a407c08d4'
        policy1_response = self.bobby_behaviors.create_bobby_policy_given(
            group_id=group_id,
            policy_id=policy_id)
        self.assertEquals(policy1_response.status_code, 201, msg='Create policy'
                          ' in bobby failed with {0}'.format(policy1_response.status_code))
        policy2_response = self.bobby_behaviors.create_bobby_policy_given(
            group_id=group_id,
            policy_id=policy_id)
        self.assertEquals(policy2_response.status_code, 403, msg='Create policy'
                          ' with already existing group and policy ID in bobby, failed'
                          ' with {0}'.format(policy2_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_without_policy_id(self):
        """
        Create a policy in bobby without a policy_id, and verify the
        response code is 400.
        """
        create_policy_response = self.bobby_client.create_bobby_policy(
            group_id=self.group_id,
            policy_id=None,
            alarm_template='9887',  # change to dict later
            check_template='987987')  # change to dict later
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy without policy_id '
                          'resulted in {0}'.format(create_policy_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_without_alarm_template(self):
        """
        Create a policy in bobby without a alarm_template, and verify the
        response code is 400.
        """
        create_policy_response = self.bobby_client.create_bobby_policy(
            group_id=self.group_id,
            alarm_template=None,
            policy_id='9887',
            check_template='987987')  # change to dict later
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy without alarm_template '
                          'resulted in {0}'.format(create_policy_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_without_check_template(self):
        """
        Create a policy in bobby without a check_template, and verify the
        response code is 400.
        """
        create_policy_response = self.bobby_client.create_bobby_policy(
            group_id=self.group_id,
            check_template=None,
            policy_id='9887',
            alarm_template='987987')  # change to dict later
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy without check_template '
                          'resulted in {0}'.format(create_policy_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_with_invalid_alarm_template(self):
        """
        Create a policy in bobby with an invalid alarm_template, and verify the
        response code is 400.
        """
        create_policy_response = self.bobby_behaviors.create_bobby_policy_given(
            alarm_template=87676876556)
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy in bobby with invalid '
                          'alarmTemplate resulted in {0}'.format(create_policy_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_with_invalid_check_template(self):
        """
        Create a policy in bobby with an invalid check_template, and verify the
        response code is 400.
        """
        create_policy_response = self.bobby_behaviors.create_bobby_policy_given(
            check_template=87676876556)
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy in bobby with invalid '
                          'checkTemplate resulted in {0}'.format(create_policy_response.status_code))

    @unittest.skip('AUTO-570')
    def test_create_group_with_nonexistant_group_id(self):
        """
        Create a policy in bobby with an nonexistant group_id, and verify the
        response code is 400.
        # currently ther is no mapping between the groupIds in the Group table and the other tables
        """
        create_policy_response = self.bobby_behaviors.create_bobby_policy_given(
            group_id='I-DONT-EXIST')
        self.assertEquals(create_policy_response.status_code, 400,
                          msg='The response code for create policy in bobby with non existant '
                          'groupId resulted in {0}'.format(create_policy_response.status_code))
