"""
Tests for the worker supervisor.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed, fail, Deferred
from twisted.internet.task import Cooperator

from zope.interface.verify import verifyObject

from otter.models.interface import IScalingGroup
from otter.supervisor import ISupervisor, SupervisorService
from otter.test.utils import iMock, patch
from otter.util.config import set_config_data


class SupervisorTests(TestCase):
    """
    Common stuff for tests in SupervisorService
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
        self.auth_function = mock.Mock(
            return_value=succeed((self.auth_token, self.service_catalog)))

        self.fake_server_details = {
            'server': {'id': 'server_id', 'links': ['links'], 'name': 'meh',
                       'metadata': {}}
        }

        set_config_data({'region': 'ORD'})
        self.addCleanup(set_config_data, {})

        self.cooperator = mock.Mock(spec=Cooperator)

        self.supervisor = SupervisorService(
            self.auth_function, self.cooperator.coiterate)

        self.InMemoryUndoStack = patch(self, 'otter.supervisor.InMemoryUndoStack')
        self.undo = self.InMemoryUndoStack.return_value
        self.undo.rewind.return_value = succeed(None)

    def test_provides_ISupervisor(self):
        """
        SupervisorService provides ISupervisor
        """
        verifyObject(ISupervisor, self.supervisor)


class LaunchConfigTests(SupervisorTests):
    """
    Test supervisor worker execution.
    """

    def setUp(self):
        """
        mock worker functions and other dependant objects
        """
        super(LaunchConfigTests, self).setUp()

        self.launch_server = patch(
            self, 'otter.supervisor.launch_server_v1.launch_server',
            return_value=succeed((self.fake_server_details, {})))
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
            self.supervisor.execute_config, self.log, 'transaction-id',
            self.group, {'type': 'not-launch_server'})

    def test_execute_config_auths(self):
        """
        execute_config asks the provided authentication function for
        credentials for the tenant_id that owns the group.
        """
        self.supervisor.execute_config(self.log, 'transaction-id',
                                       self.group, self.launch_config)

        self.auth_function.assert_called_once_with(11111)

    def test_execute_config_propogates_auth_error(self):
        """
        execute_config will propogate any errors from the authentication
        function.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        d = self.supervisor.execute_config(self.log, 'transaction-id',
                                           self.group, self.launch_config)

        (job_id, completed_d) = self.successResultOf(d)

        failure = self.failureResultOf(completed_d)
        failure.trap(ValueError)
        self.assertEquals(failure.value, expected)

    def test_execute_config_runs_launch_server_worker(self):
        """
        execute_config runs the launch_server_v1 worker with the credentials
        for the group owner.
        """
        d = self.supervisor.execute_config(self.log, 'transaction-id',
                                           self.group, self.launch_config)

        (job_id, completed_d) = self.successResultOf(d)

        result = self.successResultOf(completed_d)
        self.assertEqual(result, {'id': 'server_id', 'links': ['links'],
                                  'name': 'meh', 'lb_info': {}})

        self.launch_server.assert_called_once_with(
            mock.ANY,
            'ORD',
            self.group,
            self.service_catalog,
            self.auth_token,
            {'server': {}},
            self.undo)

    def test_execute_config_rewinds_undo_stack_on_failure(self):
        """
        execute_config rewinds the undo stack passed to launch_server,
        when launch_server fails.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        d = self.supervisor.execute_config(self.log, 'transaction-id',
                                           self.group, self.launch_config)

        (job_id, completed_d) = self.successResultOf(d)

        self.failureResultOf(completed_d)
        self.undo.rewind.assert_called_once_with()

    def test_coiterate_passed_to_undo_stack(self):
        """
        execute_config passes Supervisor's coiterate function is to
        InMemoryUndoStack.
        """
        self.supervisor.execute_config(self.log, 'transaction-id',
                                       self.group, self.launch_config)

        self.InMemoryUndoStack.assert_called_once_with(self.cooperator.coiterate)

    def test_job_deferred_added_to_deferred_pool(self):
        """
        The launch config job deferred is added to a deferred pool, if it is
        provided to the constructor
        """
        self.launch_server.return_value = Deferred()  # block forward progress

        # the pool starts off empty
        self.successResultOf(self.supervisor.deferred_pool.notify_when_empty())

        self.supervisor.execute_config(self.log, 'transaction-id',
                                       self.group, self.launch_config)

        # the pool is now not empty, since the job has been added
        empty = self.supervisor.deferred_pool.notify_when_empty()
        self.assertNoResult(empty)  # the pool is not empty now

        # after launch server returns, the pool empties
        self.launch_server.return_value.callback((self.fake_server_details, {}))
        self.successResultOf(empty)

    def test_will_not_stop_until_pool_empty(self):
        """
        The deferred returned by stopService will not fire until the deferred
        pool is empty.
        """
        self.launch_server.return_value = Deferred()  # block forward progress

        # the pool starts off empty
        self.successResultOf(self.supervisor.deferred_pool.notify_when_empty())

        self.supervisor.execute_config(self.log, 'transaction-id',
                                       self.group, self.launch_config)

        sd = self.supervisor.stopService()

        self.assertFalse(self.supervisor.running)
        self.assertNoResult(sd)

        self.launch_server.return_value.callback((self.fake_server_details, {}))

        self.successResultOf(sd)


class DeleteServerTests(SupervisorTests):
    """
    Tests for func:``otter.supervisor.execute_delete_server``
    """

    def setUp(self):
        """
        mock worker functions and other dependant objects
        """
        super(DeleteServerTests, self).setUp()
        self.delete_server = patch(
            self, 'otter.supervisor.launch_server_v1.delete_server',
            return_value=succeed(None))

        self.fake_server = self.fake_server_details['server']
        self.fake_server['lb_info'] = {}

    def test_execute_delete_calls_delete_worker(self):
        """
        ``launch_server_v1.delete_server`` is called with correct args. It is
        also logged
        """
        self.supervisor.execute_delete_server(self.log, 'transaction-id',
                                              self.group, self.fake_server)
        self.delete_server.assert_called_once_with(
            self.log.bind.return_value,
            'ORD',
            self.service_catalog,
            self.auth_token,
            (self.fake_server['id'], self.fake_server['lb_info']))
        args, _ = self.log.bind.return_value.msg.call_args
        self.assertEqual(args[0], 'Server deleted successfully')

    def test_execute_delete_error_is_logged(self):
        """
        ``launch_server_v1.delete_server`` error is logged
        """
        expected = KeyError('some')
        self.delete_server.return_value = fail(expected)

        self.supervisor.execute_delete_server(self.log, 'transaction-id',
                                              self.group, self.fake_server)

        args, kwargs = self.log.bind.return_value.err.call_args
        self.assertEqual(args[0].value, expected)
        self.assertEqual(args[1], 'Server deletion failed')

    def test_execute_delete_auths(self):
        """
        ``execute_delete_server`` asks the provided authentication function for
        credentials for the tenant_id that owns the group.
        """
        self.supervisor.execute_delete_server(self.log, 'transaction-id',
                                              self.group, self.fake_server)

        self.auth_function.assert_called_once_with(11111)

    def test_execute_delete_propogates_auth_error(self):
        """
        ``execute_delete_server`` will propogate any errors from the
        authentication function.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        self.supervisor.execute_delete_server(self.log, 'transaction-id',
                                              self.group, self.fake_server)

        args, kwargs = self.log.bind.return_value.err.call_args
        self.assertEqual(args[0].value, expected)
        self.assertEqual(args[1], 'Server deletion failed')
