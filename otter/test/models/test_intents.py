from effect import Effect, TypeDispatcher
from effect.twisted import perform

from twisted.trial.unittest import SynchronousTestCase

from otter.models.intents import ModifyGroupState, perform_modify_group_state
from otter.test.utils import mock_group


class ModifyGroupStateTests(SynchronousTestCase):
    """Tests for :func:`perform_modify_group_state`."""
    def test_perform(self):
        group = mock_group(None)
        mgs = ModifyGroupState(scaling_group=group,
                               modifier=lambda g, o: 'new state')
        dispatcher = TypeDispatcher({
            ModifyGroupState: perform_modify_group_state})
        d = perform(dispatcher, Effect(mgs))
        self.assertEqual(self.successResultOf(d), 'new state')
        self.assertEqual(group.modify_state_values, ['new state'])
