"""
Test for launch config's personality validation.
"""
import base64

from test_repo.autoscale.fixtures import AutoscaleFixture


class LaunchConfigPersonalityTest(AutoscaleFixture):

    """
    Verify launch config.
    """

    def setUp(self):
        """
        Create a scaling group.
        """
        super(LaunchConfigPersonalityTest, self).setUp()
        self.path = '/root/test.txt'

    def test_launch_config_personality_without_encoding(self):
        """
        Create a scaling group such that the server's personality in the
        launch config is not base64 encoded.
        """
        file_contents = 'This is a test file.'
        personality = [{'path': '/root/.csivh',
                        'contents': file_contents}]
        self._assert_create_group(personality)

    def test_launch_config_personality_with_invalid_personality(self):
        """
        Create a scaling group with invalid personality and verify the creation
        fails with an error 400
        """
        personalities = ['abc', 0, {'path': '/abc'}, {'contents': 'test'},
                        [{'path': self.path}], [{'content': 'test'}]]
        for personality in personalities:
            self._assert_create_group(personality)

    def test_launch_config_personality_with_max_path_size(self):
        """
        Create a scaling group with path over 255 characters and verify the creation
        fails with an error 400
        """
        long_path = 'z' * (self.personality_maxlength + 1)
        personality = [{'path': '/root/{0}.txt'.format(long_path),
                        'contents': base64.b64encode('tests')}]
        self._assert_create_group(personality)

    def test_launch_config_personality_with_max_file_content_size(self):
        """
        Create a scaling group with file contents over 1000 characters and verify the creation
        fails with an error 400
        """
        file_content = 'z' * (self.personality_max_file_size + 1)
        personality = [{'path': self.path,
                        'contents': base64.b64encode(file_content)}]
        self._assert_create_group(personality)

    def test_launch_config_personality_with_max_personalities(self):
        """
        Create a scaling group with over max personalities allowed and verify the creation
        fails with an error 400
        """
        personality_content = {'path': self.path,
                               'contents': base64.b64encode('tests')}
        personality = [personality_content for _ in range(self.max_personalities + 1)]
        self._assert_create_group(personality)

    def _assert_create_group(self, personality, response=400):
        """
        Creates a group with the given server personality.
        """
        group_response = self.autoscale_behaviors.create_scaling_group_given(
            lc_personality=personality)
        self.assertEquals(group_response.status_code, response, msg='Create group '
                          'with invalid lc_personality returned {0} as against '
                          '{1}'.format(group_response.status_code, response))
        if response is 200:
            group = group_response.entity
            self.resources.add(group, self.empty_scaling_group)
            return group
