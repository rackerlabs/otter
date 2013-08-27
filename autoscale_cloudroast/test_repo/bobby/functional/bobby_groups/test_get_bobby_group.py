"""
Test get groups in bobby
"""
from test_repo.bobby.fixtures import BobbyGroupFixture
from cloudcafe.common.tools.datagen import rand_name


class GetGroupTest(BobbyGroupFixture):

    """
    Get group tests
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a group with the given group id
        """
        cls.group_id_temp = rand_name('012345678-78f3-4543-85bc-')
        super(GetGroupTest, cls).setUpClass(group_id=cls.group_id_temp)
        cls.get_group_response = cls.bobby_client.get_group(cls.group_id_temp)
        cls.group = cls.get_group_response.entity

    def test_get_group_response(self):
        """
        Get a group, and verify the response code is 200 and validate
        the response object.
        """
        self.assertEquals(self.get_group_response.status_code, 200,
                          msg='Get group in bobby resulted in '
                          ' {0}'.format(self.get_group_response.status_code))
        self.validate_headers(self.get_group_response.headers)
        get_group = self.get_group_response.entity
        self.assert_create_bobby_group_fields(get_group, self.group_id_temp)

    def test_get_invalid_group(self):
        """
        Get a non existant group, and verify the response code is 404.
        """
        get_group_response = self.bobby_client.get_group('BUT-I-DONT-EXIST')
        self.assertEquals(get_group_response.status_code, 404,
                          msg='Get for non existant group in bobby resulted in '
                          '{0}'.format(get_group_response.status_code))
