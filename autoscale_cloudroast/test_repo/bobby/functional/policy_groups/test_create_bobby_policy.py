"""
Test to create and verify policy in bobby.
"""
from test_repo.bobby.fixtures import BobbyFixture


class CreateBobbyPolicyTest(BobbyFixture):

    """
    Verify create policy in bobby.
    """

    def test_create_bobby_policy_response(self):
        """
        Create a policy in bobby, and verify the response code is 201,
        the headers and the response object.
        """
        create_bobby_policy_response = self.bobby_behaviors.create_bobby_policy_given()
        self.assertEquals(create_bobby_policy_response.status_code, 201,
                          msg='The response code for create  group in bobby '
                          'resulted in {0}'.format(create_bobby_policy_response.status_code))
