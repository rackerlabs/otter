"""
Tests for the worker supervisor.
"""
import mock

from testtools.matchers import ContainsDict, Equals, IsInstance

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed, fail, Deferred
from twisted.internet.task import Cooperator

from zope.interface.verify import verifyObject

from otter import supervisor
from otter.models.interface import (
    IScalingGroup, GroupState, NoSuchScalingGroupError)
from otter.supervisor import (
    ISupervisor, SupervisorService, set_supervisor, remove_server_from_group,
    execute_launch_config, CannotDeleteServerBelowMinError, ServerNotFoundError)
from otter.test.utils import (
    iMock, patch, mock_log, CheckFailure, matches, FakeSupervisor, IsBoundWith,
    DummyException, mock_group)
from otter.util.deferredutils import DeferredPool


class SupervisorTests(SynchronousTestCase):
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

        self.cooperator = mock.Mock(spec=Cooperator)

        self.supervisor = SupervisorService(
            self.auth_function, 'ORD', self.cooperator.coiterate)

        self.InMemoryUndoStack = patch(self, 'otter.supervisor.InMemoryUndoStack')
        self.undo = self.InMemoryUndoStack.return_value
        self.undo.rewind.return_value = succeed(None)

    def test_provides_ISupervisor(self):
        """
        SupervisorService provides ISupervisor
        """
        verifyObject(ISupervisor, self.supervisor)


class HealthCheckTests(SupervisorTests):
    """
    Tests for supervisor health check
    """

    def test_empty(self):
        """
        When no jobs running
        """
        self.assertEqual(self.supervisor.health_check(),
                         (True, {'jobs': 0}))

    def test_filled(self):
        """
        When jobs are running, returns number of jobs running
        """
        d1, d2 = Deferred(), Deferred()
        self.supervisor.deferred_pool.add(d1)
        self.supervisor.deferred_pool.add(d2)
        self.assertEqual(self.supervisor.health_check(),
                         (True, {'jobs': 2}))
        d1.callback(None)
        self.assertEqual(self.supervisor.health_check(),
                         (True, {'jobs': 1}))
        d2.callback(None)
        self.assertEqual(self.supervisor.health_check(),
                         (True, {'jobs': 0}))


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

        self.auth_function.assert_called_once_with(
            11111, log=self.log.bind.return_value)

    def test_execute_config_propagates_auth_error(self):
        """
        execute_config will propagate any errors from the authentication
        function.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        d = self.supervisor.execute_config(self.log, 'transaction-id',
                                           self.group, self.launch_config)

        failure = self.failureResultOf(d)
        failure.trap(ValueError)
        self.assertEquals(failure.value, expected)

    def test_execute_config_runs_launch_server_worker(self):
        """
        execute_config runs the launch_server_v1 worker with the credentials
        for the group owner.
        """
        d = self.supervisor.execute_config(self.log, 'transaction-id',
                                           self.group, self.launch_config)

        result = self.successResultOf(d)
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

        self.failureResultOf(d, ValueError)
        self.undo.rewind.assert_called_once_with()

    def test_coiterate_passed_to_undo_stack(self):
        """
        execute_config passes Supervisor's coiterate function is to
        InMemoryUndoStack.
        """
        self.supervisor.execute_config(self.log, 'transaction-id',
                                       self.group, self.launch_config)

        self.InMemoryUndoStack.assert_called_once_with(self.cooperator.coiterate)

    def test_will_not_stop_until_pool_empty(self):
        """
        The deferred returned by stopService will not fire until the deferred
        pool is empty.
        """
        # the pool starts off empty
        self.successResultOf(self.supervisor.deferred_pool.notify_when_empty())

        d = Deferred()
        self.supervisor.deferred_pool.add(d)   # block forward progress

        sd = self.supervisor.stopService()

        self.assertFalse(self.supervisor.running)
        self.assertNoResult(sd)

        d.callback(None)

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

    def test_execute_delete_auths(self):
        """
        ``execute_delete_server`` asks the provided authentication function for
        credentials for the tenant_id that owns the group.
        """
        self.supervisor.execute_delete_server(self.log, 'transaction-id',
                                              self.group, self.fake_server)

        self.auth_function.assert_called_once_with(
            11111, log=self.log.bind.return_value)

    def test_execute_delete_propagates_auth_error(self):
        """
        ``execute_delete_server`` will propagate any errors from the
        authentication function.
        """
        expected = ValueError('auth failure')
        self.auth_function.return_value = fail(expected)

        d = self.supervisor.execute_delete_server(
            self.log, 'transaction-id', self.group, self.fake_server)

        f = self.failureResultOf(d, ValueError)
        self.assertEqual(f.value, expected)


class ValidateLaunchConfigTests(SupervisorTests):
    """
    Tests for func:``otter.supervisor.validate_launch_config``
    """

    def setUp(self):
        """
        mock worker functions and other dependant objects
        """
        super(ValidateLaunchConfigTests, self).setUp()
        self.log = mock.Mock()
        self.validate_launch_server_config = patch(
            self, 'otter.supervisor.validate_config.validate_launch_server_config',
            return_value=succeed(None))
        self.launch_config = {'type': 'launch_server', 'args': 'launch_args'}

    def test_valid(self):
        """
        It authenticates and calls validate_launch_server_config with correct args
        """
        d = self.supervisor.validate_launch_config(self.log, self.group.tenant_id,
                                                   self.launch_config)
        self.successResultOf(d)
        self.auth_function.assert_called_once_with(
            self.group.tenant_id, log=self.log.bind.return_value)
        self.validate_launch_server_config.assert_called_once_with(
            self.log.bind.return_value, 'ORD', self.service_catalog,
            self.auth_token, 'launch_args')

    def test_invalid_config_error_propagates(self):
        """
        Invalid launch config error is propagated
        """
        self.validate_launch_server_config.return_value = fail(ValueError('huh'))
        d = self.supervisor.validate_launch_config(self.log, self.group.tenant_id,
                                                   self.launch_config)
        f = self.failureResultOf(d, ValueError)
        self.assertEqual(f.value.args, ('huh',))

    def test_launch_server_type_check(self):
        """
        Only launch_server type is allowed
        """
        self.assertRaises(NotImplementedError, self.supervisor.validate_launch_config,
                          self.log, self.group.tenant_id, {'type': 'delete_server'})

    def test_log_binds(self):
        """
        Log is bound to tenant_id and message is logged at each step
        """
        d = self.supervisor.validate_launch_config(self.log, self.group.tenant_id,
                                                   self.launch_config)
        self.successResultOf(d)
        self.log.bind.assert_called_once_with(
            system='otter.supervisor.validate_launch_config', tenant_id=self.group.tenant_id)
        log = self.log.bind.return_value
        log.msg.assert_has_calls([mock.call('Authenticating for tenant'),
                                  mock.call('Validating launch server config')])


class FindPendingJobsToCancelTests(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.find_pending_jobs_to_cancel`
    """
    def setUp(self):
        """
        Sets up a dictionary of job ID to creation dates in order to test
        sorting.
        """
        self.data = {
            '1': {'created': '0001-01-01T00:00:05Z.0001'},
            '2': {'created': '0001-01-04T00:02:02Z'},
            '3': {'created': '0001-01-04T00:00:10Z'},
            '4': {'created': '0001-01-01T01:00:00Z.3513'},
            '5': {'created': '0001-01-05T00:00:00Z'}
        }  # ascending order by time would be: 1, 4, 3, 2, 5

        self.cancellable_state = GroupState('t', 'g', 'n', {}, self.data, None, {},
                                            False)

    def test_returns_most_recent_jobs(self):
        """
        ``find_pending_jobs_to_cancel`` returns the top ``delta`` recent jobs.
        """
        self.assertEqual(
            supervisor.find_pending_jobs_to_cancel(mock.ANY,
                                                   self.cancellable_state,
                                                   3),
            ['5', '2', '3'])

    def test_returns_all_jobs_if_delta_is_high(self):
        """
        ``find_pending_jobs_to_cancel`` returns all jobs if ``delta`` is
        greater than the length of the jobs
        """
        self.assertEqual(
            sorted(supervisor.find_pending_jobs_to_cancel(
                mock.ANY, self.cancellable_state, 100)),
            ['1', '2', '3', '4', '5'])


class FindServersToEvictTests(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.find_servers_to_evict`
    """
    def setUp(self):
        """
        Sets up a dictionary of job ID to creation dates in order to test
        sorting.
        """
        self.data = {
            '1': {'created': '0001-01-01T00:00:05Z.0001', 'id': '1',
                  'lb': 'lb'},
            '2': {'created': '0001-01-04T00:02:02Z', 'id': '2', 'lb': 'lb'},
            '3': {'created': '0001-01-04T00:00:10Z', 'id': '3', 'lb': 'lb'},
            '4': {'created': '0001-01-01T01:00:00Z.3513', 'id': '4',
                  'lb': 'lb'},
            '5': {'created': '0001-01-05T00:00:00Z', 'id': '5', 'lb': 'lb'}
        }  # ascending order by time would be: 1, 4, 3, 2, 5

        self.deletable_state = GroupState('t', 'g', 'n', self.data, {}, None, {},
                                          False)

    def test_returns_oldest_servers(self):
        """
        ``find_servers_to_evict`` returns the top ``delta`` oldest jobs.
        """
        self.assertEqual(
            supervisor.find_servers_to_evict(mock.ANY,
                                             self.deletable_state,
                                             3),
            [self.data['1'], self.data['4'], self.data['3']])

    def test_returns_all_jobs_if_delta_is_high(self):
        """
        ``find_pending_jobs_to_cancel`` returns all jobs if ``delta`` is
        greater than the length of the jobs
        """
        self.assertEqual(
            sorted(supervisor.find_servers_to_evict(
                mock.ANY, self.deletable_state, 100)),
            sorted(self.data.values()))


class DeleteActiveServersTests(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.delete_active_servers`
    """

    def setUp(self):
        """
        mock all the dependent functions and data
        """
        self.log = mock.Mock()
        self.data = {
            '1': {'created': '0001-01-01T00:00:05Z.0001', 'id': '1',
                  'lb': 'lb'},
            '2': {'created': '0001-01-04T00:02:02Z', 'id': '2', 'lb': 'lb'},
            '3': {'created': '0001-01-04T00:00:10Z', 'id': '3', 'lb': 'lb'},
            '4': {'created': '0001-01-01T01:00:00Z.3513', 'id': '4',
                  'lb': 'lb'},
            '5': {'created': '0001-01-05T00:00:00Z', 'id': '5', 'lb': 'lb'}
        }  # ascending order by time would be: 1, 4, 3, 2, 5
        self.fake_state = GroupState('t', 'g', 'n', self.data, {}, False, False,
                                     False)
        self.evict_servers = {'1': self.data['1'], '4': self.data['4'],
                              '3': self.data['3']}

        self.find_servers_to_evict = patch(
            self, 'otter.supervisor.find_servers_to_evict',
            return_value=self.evict_servers.values())

        self.jobs = [mock.Mock(), mock.Mock(), mock.Mock()]
        self.del_job = patch(
            self, 'otter.supervisor._DeleteJob', side_effect=self.jobs)

        self.supervisor = iMock(ISupervisor)
        self.supervisor.deferred_pool = DeferredPool()
        patch(self, 'otter.supervisor.get_supervisor',
              return_value=self.supervisor)

    def test_success(self):
        """
        Removes servers to evict from state and create `_DeleteJob` to start
        deleting them
        """
        supervisor.delete_active_servers(self.log, 'trans-id', 'group',
                                         3, self.fake_state)

        # find_servers_to_evict was called
        self.find_servers_to_evict.assert_called_once_with(
            self.log, self.fake_state, 3)

        # active servers removed from state
        self.assertTrue(
            all([_id not in self.fake_state.active for _id in self.evict_servers]))

        # _DeleteJob was created for each server to delete
        self.assertEqual(
            self.del_job.call_args_list,
            [mock.call(self.log, 'trans-id', 'group', data, self.supervisor)
                for i, data in enumerate(self.evict_servers.values())])

        # They were started
        self.assertTrue(all([job.start.called for job in self.jobs]))


class DeleteJobTests(SynchronousTestCase):
    """
    Tests for :class:`supervisor._DeleteJob`
    """

    def setUp(self):
        """
        Create sample _DeleteJob
        """
        self.supervisor = iMock(ISupervisor)
        log = mock.Mock()
        self.job = supervisor._DeleteJob(log, 'trans_id', 'group', {'id': 2, 'b': 'lah'},
                                         self.supervisor)
        log.bind.assert_called_once_with(system='otter.job.delete', server_id=2)
        self.log = log.bind.return_value

    def test_start(self):
        """
        `start` calls `supervisor.execute_delete_server`
        """
        self.job.start()

        self.supervisor.execute_delete_server.assert_called_once_with(
            self.log, 'trans_id', 'group', {'id': 2, 'b': 'lah'})
        d = self.supervisor.execute_delete_server.return_value
        d.addCallback.assert_called_once_with(self.job._job_completed)
        d.addErrback.assert_called_once_with(self.job._job_failed)
        self.log.msg.assert_called_once_with('Started server deletion job')

    def test_job_completed(self):
        """
        `_job_completed` audit logs a successful deletion
        """
        log = self.job.log = mock_log()
        self.job._job_completed('ignore')
        log.msg.assert_called_with('Server deleted.', audit_log=True,
                                   event_type='server.delete')

    def test_job_failed(self):
        """
        `_job_failed` logs failure
        """
        self.supervisor.execute_delete_server.return_value = fail(ValueError('a'))
        self.job.start()
        self.log.err.assert_called_once_with(CheckFailure(ValueError),
                                             'Server deletion job failed')


class ExecScaleDownTests(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.exec_scale_down`
    """

    def setUp(self):
        """
        mock dependent objects and functions
        """
        self.log = mock.Mock()
        self.pending = {
            '1': {'created': '0001-01-01T00:00:05Z.0001'},
            '2': {'created': '0001-01-04T00:02:02Z'},
            '3': {'created': '0001-01-04T00:00:10Z'},
            '4': {'created': '0001-01-01T01:00:00Z.3513'},
            '5': {'created': '0001-01-05T00:00:00Z'}
        }  # descending order by time would be: 5, 2, 3, 4, 1
        self.active = {
            'a1': {'created': '0001-01-01T00:00:05Z.0001', 'id': '1',
                   'lb': 'lb'},
            'a2': {'created': '0001-01-04T00:02:02Z', 'id': '2', 'lb': 'lb'},
            'a3': {'created': '0001-01-04T00:00:10Z', 'id': '3', 'lb': 'lb'},
            'a4': {'created': '0001-01-01T01:00:00Z.3513', 'id': '4',
                   'lb': 'lb'},
            'a5': {'created': '0001-01-05T00:00:00Z', 'id': '5', 'lb': 'lb'}
        }  # ascending order by time would be: a1, a4, a3, a2, a5
        self.fake_state = GroupState('t', 'g', '', self.active, self.pending,
                                     False, False, False)
        self.find_pending_jobs_to_cancel = patch(
            self, 'otter.supervisor.find_pending_jobs_to_cancel')
        self.del_active_servers = patch(
            self, 'otter.supervisor.delete_active_servers')

    def test_pending_jobs_removed(self):
        """
        Pending jobs are removed from state
        """
        exp_pending_jobs = ['5', '2', '3']
        self.find_pending_jobs_to_cancel.return_value = exp_pending_jobs
        supervisor.exec_scale_down(self.log, 'tid', self.fake_state, 'g', 3)
        for job_id in exp_pending_jobs:
            self.assertNotIn(job_id, self.fake_state.pending)

    def test_del_active_servers_called(self):
        """
        ``delete_active_servers`` is called with correct arguments
        """
        self.find_pending_jobs_to_cancel.return_value = self.pending.keys()
        supervisor.exec_scale_down(self.log, 'tid', self.fake_state, 'g', 7)
        self.del_active_servers.assert_called_once_with(self.log, 'tid',
                                                        'g', 2,
                                                        self.fake_state)

    def test_del_active_servers_not_called(self):
        """
        ``delete_active_servers`` is not called when pending jobs are enough
        """
        self.find_pending_jobs_to_cancel.return_value = ['5', '2', '3']
        supervisor.exec_scale_down(self.log, 'tid', self.fake_state, 'g', 3)
        self.assertFalse(self.del_active_servers.called)


class ExecuteLaunchConfigTestCase(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.execute_launch_config`
    """

    def setUp(self):
        """
        Setup fake supervisor and fake job
        """
        self.supervisor = FakeSupervisor()
        set_supervisor(self.supervisor)
        self.addCleanup(set_supervisor, None)

        self.log = mock_log()

        self.jobs = []

        class FakeJob(object):

            def __init__(jself, *args):
                jself.args = args
                jself.job_id = len(self.jobs) + 10
                self.jobs.append(jself)

            def start(jself, launch):
                jself.launch = launch
                jself.d = Deferred()
                return jself.d

        patch(self, 'otter.supervisor._Job', new=FakeJob)
        self.state = GroupState('t', 'g', 'n', {}, {}, *range(3))

    def test_no_jobs_started(self):
        """
        If delta == 0, ``execute_launch_config`` does not create any job. It also logs
        """
        d = execute_launch_config(self.log, 'tid', self.state, 'launch', 'group', 0)
        self.assertIsNone(self.successResultOf(d))

        self.log.msg.assert_called_once_with('Launching {delta} servers.', delta=0)
        self.assertEqual(len(self.jobs), 0)

    def test_delta_jobs_started(self):
        """
        If delta > 0, ``execute_launch_config`` creates and starts delta jobs.
        It adds the jobs to the state and its completion deferreds to supervisor's pool.
        It also logs
        """
        d = execute_launch_config(self.log, 'tid', self.state, 'launch', 'group', 3)
        self.assertIsNone(self.successResultOf(d))

        self.log.msg.assert_called_once_with('Launching {delta} servers.', delta=3)

        self.assertEqual(len(self.jobs), 3)
        for job in self.jobs:
            self.assertEqual(job.args, (self.log, 'tid', 'group', self.supervisor))
            self.assertEqual(job.launch, 'launch')
            self.assertIn(job.job_id, self.state.pending)
            self.assertIn(job.d, self.supervisor.deferred_pool)


class PrivateJobHelperTestCase(SynchronousTestCase):
    """
    Tests for the private helper class `_Job`
    """
    def setUp(self):
        """
        Mock a fake supervisor, and also a fake log and group.
        """
        self.transaction_id = 'transaction_id'
        self.job_id = 'job_id'
        patch(self, 'otter.supervisor.generate_job_id', return_value=self.job_id)
        self.state = GroupState('tenant', 'group', 'name', {}, {}, None, {}, False)
        self.group = mock_group(self.state, 'tenant', 'group')

        self.supervisor = iMock(ISupervisor)
        self.supervisor.deferred_pool = DeferredPool()
        self.completion_deferred = Deferred()
        self.supervisor.execute_config.return_value = self.completion_deferred

        self.log = mock_log()
        self.job = supervisor._Job(self.log, self.transaction_id, self.group,
                                   self.supervisor)

        self.del_job = patch(self, 'otter.supervisor._DeleteJob')
        self.mock_launch = {'type': 'launch_server',
                            'args': {'server': {'imageRef': 'imageID',
                                                'flavorRef': '1'}}}

    def test_start_binds_invalid_image_ref_to_log(self):
        """
        `start` binds the image ID to a string that says that we were unable
        to find the image id in the logs, if the image ref could not be found
        """
        del self.mock_launch['args']['server']['imageRef']
        self.job.start(self.mock_launch)
        self.assertEqual(
            self.job.log,
            matches(IsBoundWith(system='otter.job.launch',
                                image_ref="Unable to pull image ref.",
                                flavor_ref='1', job_id='job_id')))

    def test_start_binds_invalid_flavor_ref_to_log(self):
        """
        `start` binds the flavor ID to a string that says that we were unable
        to find the flavor id in the logs, if the flavor ref could not be found
        """
        del self.mock_launch['args']['server']['flavorRef']
        self.job.start(self.mock_launch)
        self.assertEqual(
            self.job.log,
            matches(IsBoundWith(system='otter.job.launch', image_ref="imageID",
                                flavor_ref="Unable to pull flavor ref.",
                                job_id='job_id')))

    def test_start_calls_supervisor(self):
        """
        `start` calls the supervisor's `execute_config` method with
        log bound with imageRef and flavorRef from launch config
        """
        self.job.start(self.mock_launch)
        self.supervisor.execute_config.assert_called_once_with(
            matches(IsBoundWith(system='otter.job.launch', image_ref="imageID",
                                flavor_ref='1', job_id='job_id')),
            self.transaction_id,
            self.group, self.mock_launch)

    def test_modify_state_called_on_job_completion_success(self):
        """
        If the job succeeded, and modify_state is called
        """
        self.job.start('launch')
        self.assertEqual(self.group.modify_state.call_count, 0)
        self.completion_deferred.callback({'id': 'blob'})
        self.assertEqual(self.group.modify_state.call_count, 1)

    def test_modify_state_called_on_job_completion_failure(self):
        """
        If the job failed, modify_state is called
        """
        self.job.start('launch')
        self.assertEqual(self.group.modify_state.call_count, 0)
        self.completion_deferred.errback(Exception('e'))
        self.assertEqual(self.group.modify_state.call_count, 1)

    def test_job_completion_success_job_marked_as_active(self):
        """
        If the job succeeded, and the job ID is still in pending, it is removed
        and added to active.
        """
        self.state.add_job(self.job_id)
        self.job.start('launch')
        self.completion_deferred.callback({'id': 'active'})

        self.assertIs(self.successResultOf(self.completion_deferred),
                      self.state)

        self.assertEqual(self.state.pending, {})
        self.assertEqual(
            self.state.active,
            {'active': matches(ContainsDict({'id': Equals('active')}))})

    def test_job_completion_success_audit_logged(self):
        """
        If the job succeeded, and the job ID is still in pending, it is audit
        logged as a "server.active" event, and the new state after the server
        has been moved to active is logged.
        """
        self.state.add_job(self.job_id)
        self.state.desired = 1
        self.job.start(self.mock_launch)
        self.completion_deferred.callback({'id': 'yay'})

        self.successResultOf(self.completion_deferred)

        self.log.msg.assert_called_once_with(
            "Server is active.", event_type="server.active", server_id='yay',
            job_id=self.job_id, audit_log=True, system="otter.job.launch",
            image_ref="imageID", flavor_ref="1", current_active=1,
            current_pending=0, current_desired=1)

    def test_job_completion_success_job_deleted_pending(self):
        """
        If the job succeeded, but the job ID is no longer in pending, the
        server is deleted and the state not changed.  No error is logged.
        """
        d = Deferred()
        self.del_job.return_value.start.return_value = d

        self.job.start('launch')
        self.completion_deferred.callback({'id': 'active'})

        self.assertIs(self.successResultOf(self.completion_deferred),
                      self.state)

        self.assertEqual(self.state.pending, {})
        self.assertEqual(self.state.active, {})

        self.del_job.assert_called_once_with(
            matches(IsInstance(self.log.__class__)), self.transaction_id,
            self.group, {'id': 'active'}, self.supervisor)
        self.assertIn(d, self.supervisor.deferred_pool)

        self.assertEqual(self.log.err.call_count, 0)

    def test_job_completion_success_job_deleted_audit_logged(self):
        """
        If the job succeeded, but the job ID is no longer in pending, it is
        audit logged as a "server.deletable" event.
        """
        self.state = GroupState('tenant', 'group', 'name', {}, {}, None,
                                {}, False, desired=0)
        self.job.start(self.mock_launch)
        self.completion_deferred.callback({'id': 'yay'})

        self.successResultOf(self.completion_deferred)

        self.log.msg.assert_called_once_with(
            ("A pending server that is no longer needed is now active, "
             "and hence deletable.  Deleting said server."),
            event_type="server.deletable", server_id='yay', job_id=self.job_id,
            audit_log=True, system="otter.job.launch", image_ref="imageID",
            flavor_ref="1", current_active=0, current_pending=0,
            current_desired=0)

    def test_job_completion_failure_job_removed(self):
        """
        If the job failed, the job ID is removed from the pending state.  The
        failure is logged.
        """
        self.state.add_job(self.job_id)
        self.job.start(self.mock_launch)
        self.completion_deferred.errback(DummyException('e'))

        self.assertIs(self.successResultOf(self.completion_deferred),
                      self.state)

        self.assertEqual(self.state.pending, {})
        self.assertEqual(self.state.active, {})

        self.log.err.assert_called_once_with(
            CheckFailure(DummyException), 'Launching server failed',
            system="otter.job.launch", image_ref="imageID", job_id=self.job_id,
            flavor_ref="1", current_active=0, current_pending=0,
            current_desired=0)

    def test_job_completion_failure_job_deleted_pending(self):
        """
        If the job failed, but the job ID is no longer in pending, the job id
        is not removed (and hence no error occurs).  The only error logged is
        the failure. Nothing else in the state changes.
        """
        self.job.start(self.mock_launch)
        self.completion_deferred.errback(DummyException('e'))

        self.assertIs(self.successResultOf(self.completion_deferred),
                      self.state)

        self.assertEqual(self.state.pending, {})
        self.assertEqual(self.state.active, {})

        self.log.err.assert_called_with(
            CheckFailure(DummyException), 'Launching server failed',
            system="otter.job.launch", image_ref="imageID", job_id=self.job_id,
            flavor_ref="1", current_active=0, current_pending=0,
            current_desired=0)

    def test_job_completion_success_NoSuchScalingGroupError(self):
        """
        If a job is completed successfully, but `modify_state` fails with a
        `NoSuchScalingGroupError`, then the group has been deleted and so the
        server is deleted
        """
        self.group.modify_state.side_effect = (
            lambda *args: fail(NoSuchScalingGroupError('tenant', 'group')))
        d = Deferred()
        self.del_job.return_value.start.return_value = d

        self.job.start('launch')
        self.completion_deferred.callback({'id': 'active'})

        self.del_job.assert_called_once_with(
            matches(IsInstance(self.log.__class__)), self.transaction_id,
            self.group, {'id': 'active'}, self.supervisor)
        self.del_job.return_value.start.assert_called_once_with()
        self.assertIn(d, self.supervisor.deferred_pool)

    def test_job_completion_success_NoSuchScalingGroupError_audit_logged(self):
        """
        If the job succeeded, but the job ID is no longer in pending, it is
        audit logged as a "server.deletable" event.
        """
        self.group.modify_state.side_effect = (
            lambda *args: fail(NoSuchScalingGroupError('tenant', 'group')))

        self.job.start(self.mock_launch)
        self.completion_deferred.callback({'id': 'yay'})

        self.successResultOf(self.completion_deferred)

        self.log.msg.assert_called_once_with(
            ("A pending server belonging to a deleted scaling group "
             "({scaling_group_id}) is now active, and hence deletable. "
             "Deleting said server."),
            event_type="server.deletable", server_id='yay', job_id=self.job_id,
            audit_log=True, system="otter.job.launch", image_ref="imageID",
            flavor_ref="1")

    def test_job_completion_failure_NoSuchScalingGroupError(self):
        """
        If a job fails, but `modify_state` fails with a
        `NoSuchScalingGroupError`, then the group has been deleted and the
        failure can be ignored (not logged)
        """
        self.group.modify_state.side_effect = (
            lambda *args: fail(NoSuchScalingGroupError('tenant', 'group')))

        self.job.start('launch')
        self.completion_deferred.callback({'id': 'active'})
        self.assertEqual(self.log.err.call_count, 0)

    def test_modify_state_failure_logged(self):
        """
        If `modify_state` fails with a non-`NoSuchScalingGroupError`, the error
        is logged
        """
        self.group.modify_state.side_effect = (
            lambda *args: fail(DummyException('e')))

        self.job.start(self.mock_launch)
        self.completion_deferred.callback({'id': 'active'})

        self.log.err.assert_called_once_with(CheckFailure(DummyException),
                                             system="otter.job.launch",
                                             image_ref="imageID", flavor_ref="1",
                                             job_id=self.job_id)


class RemoveServerTests(SynchronousTestCase):
    """
    Tests for :func:`otter.supervisor.remove_server_from_group`
    """

    def setUp(self):
        """
        Fake supervisor, group and state
        """
        self.tid = 'trans_id'
        self.log = mock_log()
        self.state = GroupState('tid', 'gid', 'g', {'s0': {'id': 's0'}}, {},
                                None, None, None, desired=1)
        self.group = mock_group(self.state)
        self.gen_jobid = patch(self, 'otter.supervisor.generate_job_id', return_value='jid')
        self.supervisor = FakeSupervisor()
        set_supervisor(self.supervisor)
        self.addCleanup(set_supervisor, None)

        self.group.view_config.return_value = succeed({'minEntities': 0})
        self.group.view_launch_config.return_value = succeed('launch')

    def _remove_server(self, replace=True, purge=True, server_id="s0"):
        """
        Try to remove a server from the group.
        """
        d = remove_server_from_group(self.log, self.tid, server_id,
                                     replace, purge, self.group, self.state)
        return d

    def _assert_server_in_group_state(self, state):
        """
        Assert that the server is still in the group state.
        """
        self.assertEqual(state.active, {'s0': {'id': 's0'}})

    def _assert_server_not_in_group_state(self, state):
        """
        Assert that the server is not in the group state.
        """
        self.assertNotIn('s0', state.active)

    def _assert_delete_scheduled(self):
        """
        Assert that the server was scheduled for deletion.
        """
        self.assertEqual(self.supervisor.del_calls[-1],
                         (matches(IsBoundWith(server_id='s0', system='otter.job.delete')),
                          self.tid, self.group, {'id': 's0'}))

    def _assert_delete_not_scheduled(self):
        """
        Assert that the server was scheduled for deletion.
        """
        self.assertEqual(self.supervisor.del_calls, [])

    def _assert_create_scheduled(self, state):
        """
        Assert that a new server is being created. Specifically, checks
        that the id is now pending, and that the supervisor has a
        create server call.
        """
        self.assertIn('jid', state.pending)
        self.assertEqual(self.supervisor.exec_calls[-1],
                         (matches(IsBoundWith(image_ref=mock.ANY,
                                              flavor_ref=mock.ANY,
                                              system='otter.job.launch',
                                              job_id='jid')),
                          self.tid, self.group, 'launch'))

    def _assert_create_not_scheduled(self, state):
        """
        Assert that a new server is not being created. Specifically,
        checks that the id does not exist in pending, and no creation
        calls were issued.
        """
        self.assertNotIn('jid', state.pending)
        self.assertEqual(self.supervisor.exec_calls, [])

    def test_server_not_found(self):
        """
        If specific server is not in the group, :class:`ServerNotFoundError`
        is raised.
        """
        self.assertRaises(ServerNotFoundError,
                          self._remove_server, server_id="BOGUS")

        self._assert_server_in_group_state(self.state)
        self._assert_create_not_scheduled(self.state)
        self._assert_delete_not_scheduled()
        self.assertEqual(self.state.desired, 1)

    def test_not_deleted_below_min(self):
        """
        :class:`CannotDeleteServerBelowMinError` is raised if the current
        (active + pending) number of servers is already the minimum.
        """
        self.state.add_job('j1')
        self.group.view_config.return_value = succeed({'minEntities': 2})
        d = self._remove_server(replace=False, purge=True)
        self.failureResultOf(d, CannotDeleteServerBelowMinError)

        self._assert_server_in_group_state(self.state)
        self._assert_delete_not_scheduled()
        self._assert_create_not_scheduled(self.state)
        self.assertEqual(self.state.desired, 1)

    def test_replaced_and_removed(self):
        """
        Server is removed, purged and replaced.
        """
        d = self._remove_server(replace=True, purge=True)
        state = self.successResultOf(d)

        self._assert_server_not_in_group_state(state)
        self._assert_delete_scheduled()
        self._assert_create_scheduled(state)
        self.assertEqual(self.state.desired, 1)

    def test_not_replaced(self):
        """
        Server is removed and purged from Nova, but not replaced. The
        desired is reduced by 1.
        """
        d = self._remove_server(replace=False, purge=True)
        state = self.successResultOf(d)

        self._assert_server_not_in_group_state(state)
        self._assert_delete_scheduled()
        self._assert_create_not_scheduled(state)
        self.assertEqual(state.desired, 0)

    def test_not_replaced_and_not_purged(self):
        """
        The server is removed, but not replaced and not purged.
        """
        d = self._remove_server(replace=False, purge=False)
        state = self.successResultOf(d)

        self._assert_server_not_in_group_state(state)
        self._assert_delete_not_scheduled()
        self._assert_create_not_scheduled(state)
        self.assertEqual(state.desired, 0)

    def test_replaced_but_not_purged(self):
        """
        The server is removed, replaced, but not purged.
        """
        d = self._remove_server(replace=True, purge=False)
        state = self.successResultOf(d)

        self._assert_server_not_in_group_state(state)
        self._assert_delete_not_scheduled()
        self._assert_create_scheduled(state)
        self.assertEqual(state.desired, 1)
