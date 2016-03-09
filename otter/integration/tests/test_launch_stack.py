"""
Tests covering Otter's integration with Heat for the launch_stack launch
configuration.
"""

from pyrsistent import pbag

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.log import msg
from twisted.trial import unittest

from otter.convergence.model import get_stack_tag_for_group

from otter.integration.lib.autoscale import ScalingGroup, ScalingPolicy
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    region,
    timeout)

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    terminal_errors_except
)


class TestLaunchStack(unittest.TestCase):
    """Tests making sure launch_stack launch configurations can be used."""

    def setUp(self):
        """
        Establish an HTTP connection pool and commonly used resources for each
        test. The HTTP connection pool is important for maintaining a clean
        Twisted reactor.
        """
        self.helper = TestHelper(self)
        self.rcs = TestResources()
        self.identity = get_identity(self.helper.pool)

        scaling_group_config = {
            'launchConfiguration': {
                'args': {
                    'stack': {
                        'template': {
                            'heat_template_version': '2015-04-30',
                            'resources': {
                                'rand': {'type': 'OS::Heat::RandomString'}
                            }
                        }
                    }
                },
                'type': 'launch_stack'
            },
            'groupConfiguration': {
                'name': 'test_launch_stack',
                'cooldown': 0,
                'minEntities': 0,
                'maxEntities': 10
            },
            'scalingPolicies': [],
        }

        self.group = ScalingGroup(group_config=scaling_group_config,
                                  treq=self.helper.treq,
                                  pool=self.helper.pool)

        return self.identity.authenticate_user(
            self.rcs, resources=get_resource_mapping(), region=region)

    def get_stack_list(self):
        return (self.helper.treq.get(
                    '{}/stacks'.format(self.rcs.endpoints['heat']),
                    headers=headers(str(self.rcs.token)),
                    params={
                        'tags': get_stack_tag_for_group(self.group.group_id)},
                    pool=self.helper.pool)
                .addCallback(check_success, [200])
                .addCallback(self.helper.treq.json_content))

    def wait_for_stack_list(self, expected_states, timeout=180, period=10):
        def check(content):
            states = pbag([s['stack_status'] for s in content['stacks']])
            if not (states == expected_states):
                msg("Waiting for group {} to reach desired group state.\n"
                    "{} (actual) {} (expected)"
                    .format(self.group.group_id, states, expected_states))
                raise TransientRetryError(
                    "Group states of {} did not match expected {})"
                    .format(states, expected_states))

            msg("Success: desired group state reached:\n{}"
                .format(expected_states))
            return self.rcs

        def poll():
            return self.get_stack_list().addCallback(check)

        expected_states = pbag(expected_states)

        return retry_and_timeout(
            poll, timeout,
            can_retry=terminal_errors_except(TransientRetryError),
            next_interval=repeating_interval(period),
            clock=reactor,
            deferred_description=(
                "Waiting for group {} to reach state {}".format(
                    self.group.group_id, str(expected_states))))

    @timeout(180 * 3 + 10)
    @inlineCallbacks
    def test_create(self):
        """
        For a launch_stack config, stacks are created, checked, updated, and
        deleted through Heat.
        """
        p = ScalingPolicy(set_to=5, scaling_group=self.group)
        scale_up = ScalingPolicy(set_to=7, scaling_group=self.group)
        scale_down = ScalingPolicy(set_to=1, scaling_group=self.group)

        yield self.group.start(self.rcs, self)

        yield p.start(self.rcs, self)
        yield p.execute(self.rcs)
        yield self.wait_for_stack_list([u'UPDATE_COMPLETE'] * 5)

        yield scale_up.start(self.rcs, self)
        yield scale_up.execute(self.rcs)
        yield self.wait_for_stack_list(
            [u'UPDATE_COMPLETE'] * 5 + [u'CREATE_COMPLETE'] * 2)

        yield scale_down.start(self.rcs, self)
        yield scale_down.execute(self.rcs)
        yield self.wait_for_stack_list([u'UPDATE_COMPLETE'])
