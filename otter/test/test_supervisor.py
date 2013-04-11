"""
Tests for the worker supervisor.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed, fail

from otter.models.interface import IScalingGroup
from otter.supervisor import execute_config
from otter.test.utils import iMock, patch


class SupervisorExecuteTests(TestCase):
    """
    Test supervisor worker execution.
    """

    def setUp(self):
        """
        Configure test resources.
        """
        self.log = mock.Mock()
        self.group = iMock(IScalingGroup)
        self.group.tenant_id = 11111
        self.group.uuid = 'group-id'

        self.auth_token = 'auth-token'
        self.service_catalog = {}
        self.auth_function = mock.Mock(return_value=succeed((self.auth_token, self.service_catalog)))

        self.launch_server = patch(self, 'otter.supervisor.launch_server_v1.launch_server')
        self.generate_job_id = patch(self, 'otter.supervisor.generate_job_id')
        self.generate_job_id.return_value = 'job-id'
        self.launch_config = {'type': 'launch_server',
                              'args': {'server': {}}}

    def test_only_allow_launch_server(self):
        """
        execute_config only allows launch_server currently.
        """
        self.assertRaises(
            AssertionError,
            execute_config, self.log, 'transaction-id', self.auth_function,
            self.group, {'type': 'not-launch_server'})

    def test_execute_config_auths(self):
        """
        execute_config asks the provided authentication function for
        credentials for the tenant_id that owns the group.
        """
        execute_config(self.log, 'transaction-id', self.auth_function,
                       self.group, self.launch_config)

        self.auth_function.assert_called_once_with(11111)

    def test_execute_config_propogates_auth_error(self):
        """
        execute_config will propogate any errors from the authentication function.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        d = execute_config(self.log, 'transaction-id', self.auth_function,
                           self.group, self.launch_config)

        (job_id, completed_d, job_info) = self.successResultOf(d)

        failure = self.failureResultOf(completed_d)
        failure.trap(ValueError)
        self.assertEquals(failure.value, expected)

    def test_execute_config_runs_launch_server_worker(self):
        """
        execute_config runs the launch_server_v1 worker with the credentials
        for the group owner.
        """
        d = execute_config(self.log, 'transaction-id', self.auth_function,
                           self.group, self.launch_config)

        (job_id, completed_d, job_info) = self.successResultOf(d)

        result = self.successResultOf(completed_d)
        self.assertEqual(None, result)

        self.launch_server.assert_called_once_with(
            'ORD',
            self.group,
            self.service_catalog,
            self.auth_token,
            {'server': {}})
