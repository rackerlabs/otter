"""Tests for otter.util.zk"""

from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.util.zk import DELETE_NODE, create_or_update, update_or_delete


class ZNodeStatStub(object):
    """Like a :obj:`ZNodeStat`, but only supporting the data we need."""
    def __init__(self, version):
        self.version = version


class ZKCrudModel(object):
    """
    A simplified model of Kazoo's CRUD operations, supporting
    version-check-and-set.

    To facilitate testing tricky concurrent scenarios, a system of 'post-hooks'
    is provided, which allows calling an arbitrary function immediately after
    some operations take effect.
    """
    def __init__(self):
        self.nodes = {}

    def create(self, path, content, makepath=False):
        assert makepath is True, "makepath must be True"
        if path in self.nodes:
            return fail(NodeExistsError("{} already exists".format(path)))
        self.nodes[path] = (content, 0)
        return succeed(path)

    def get(self, path):
        if path not in self.nodes:
            return fail(NoNodeError("{} does not exist".format(path)))
        content, version = self.nodes[path]
        return succeed((content, ZNodeStatStub(version)))

    def _check_version(self, path, version):
        assert version != -1, "version must be specified"
        if path not in self.nodes:
            return fail(NoNodeError("{} does not exist".format(path)))
        current_version = self.nodes[path][1]
        if current_version != version:
            return fail(BadVersionError(
                "When operating on {}, version {} was specified by version "
                "{} was found".format(path, version, current_version)))

    def set(self, path, new_value, version=-1):
        check = self._check_version(path, version)
        if check is not None:
            return check
        new_stat = ZNodeStatStub(version + 1)
        self.nodes[path] = (new_value, new_stat.version)
        return succeed(new_stat)

    def delete(self, path, version=-1):
        check = self._check_version(path, version)
        if check is not None:
            return check
        del self.nodes[path]
        return succeed(None)


class CreateOrUpdateTests(SynchronousTestCase):
    """Tests for :func:`create_or_update`."""

    def setUp(self):
        self.model = ZKCrudModel()

    def test_create(self):
        """
        New nodes are created with the initial value, and the initial value is
        returned.
        """
        d = create_or_update(self.model, '/foo', lambda x: 1 / 0, 'initial')
        self.assertEqual(self.successResultOf(d), 'initial')
        self.assertEqual(self.model.nodes, {'/foo': ('initial', 0)})

    def test_update(self):
        """
        When a node already exists, its existing content is used to update it,
        and the new value is returned.
        """
        self.model.create('/foo', 'bar', makepath=True)
        d = create_or_update(self.model, '/foo', lambda x: x + '!', 'initial')
        self.assertEqual(self.successResultOf(d), 'bar!')
        self.assertEqual(self.model.nodes, {'/foo': ('bar!', 1)})

    def test_node_disappeared_during_retrieval(self):
        """
        When the node unexpectedly disappears while retrieving the current
        content, it is recreated with the initial value, and the initial value
        is returned.
        """
        # Scenario: `/foo` already exists, but then it disappears right before
        # the `get`.
        self.model.create('/foo', 'already-exists', makepath=True)

        def get_foo(path):
            self.model.delete('/foo', version=0)
            return ZKCrudModel.get(self.model, path)
        self.model.get = get_foo

        d = create_or_update(self.model, '/foo', lambda x: x + '!', 'initial')
        self.assertEqual(self.successResultOf(d), 'initial')
        self.assertEqual(self.model.nodes, {'/foo': ('initial', 0)})

    def test_version_mismatch_during_set(self):
        """
        When the node has been updated independently in between getting and
        setting the content, the check-and-set is retried.
        """
        # Scenario: `/foo` already exists, but right after the `get` it gets
        # updated concurrently by another actor.
        self.model.create('/foo', 'already-exists', makepath=True)

        def get_foo(path):
            content, version = self.model.nodes[path]
            self.model.set(path, 'wibble', version=version)
            del self.model.get  # only run this behavior once
            return succeed((content, ZNodeStatStub(version)))

        self.model.get = get_foo

        d = create_or_update(self.model, '/foo', lambda x: x + '!', 'initial')
        self.assertEqual(self.successResultOf(d), 'wibble!')
        self.assertEqual(self.model.nodes, {'/foo': ('wibble!', 2)})

    def test_node_disappeared_during_setting(self):
        """
        When the node unexpectedly disappears while setting the new content, it
        is recreated with the initial value.
        """
        # Scenario: `/foo` already exists, but right after the `get` it's
        # deleted.
        self.model.create('/foo', 'already-exists', makepath=True)

        def get_foo(path):
            content, version = self.model.nodes[path]
            self.model.delete(path, version=version)
            return succeed((content, ZNodeStatStub(version)))

        self.model.get = get_foo

        d = create_or_update(self.model, '/foo', lambda x: x + '!', 'initial')
        self.assertEqual(self.successResultOf(d), 'initial')
        self.assertEqual(self.model.nodes, {'/foo': ('initial', 0)})


class UpdateOrDeleteTests(SynchronousTestCase):
    """Tests for :func:`update_or_delete`."""

    def setUp(self):
        self.model = ZKCrudModel()

    def test_no_node(self):
        """
        When the node doesn't already exist, :obj:`NoNodeError` bubbles up.
        """
        d = update_or_delete(self.model, '/foo', lambda x: 1 / 0)
        self.failureResultOf(d, NoNodeError)
        self.assertEqual(self.model.nodes, {})

    def test_update(self):
        """
        Existing content is used to calculate new content, and the new value is
        returned.
        """
        self.model.create('/foo', 'initial', makepath=True)
        d = update_or_delete(self.model, '/foo', lambda x: x + '!')
        self.assertEqual(self.successResultOf(d), 'initial!')
        self.assertEqual(self.model.nodes, {'/foo': ('initial!', 1)})

    def test_delete(self):
        """
        When the update function returns DELETE_NODE, the node is deleted.
        """
        self.model.create('/foo', 'initial', makepath=True)
        d = update_or_delete(self.model, '/foo', lambda x: DELETE_NODE)
        self.assertIs(self.successResultOf(d), DELETE_NODE)
        self.assertEqual(self.model.nodes, {})

    def test_version_mismatch_during_set(self):
        """
        When the node has been updated independently in between getting and
        setting the content, the check-and-set is retried.
        """
        # Scenario: `/foo` already exists, but right after the `get` it gets
        # updated concurrently by another actor.
        self.model.create('/foo', 'update-me', makepath=True)

        def get_foo(path):
            content, version = self.model.nodes[path]
            self.model.set(path, 'wibble', version=version)
            del self.model.get  # only run this behavior once
            return succeed((content, ZNodeStatStub(version)))

        self.model.get = get_foo

        def update_func(original):
            if original == 'update-me':
                return original + '!'
            elif original == 'wibble':
                return 'WIBBLE'
        d = update_or_delete(self.model, '/foo', update_func)
        self.assertEqual(self.successResultOf(d), 'WIBBLE')
        self.assertEqual(self.model.nodes, {'/foo': ('WIBBLE', 2)})

    def test_version_mismatch_during_delete(self):
        """
        When the node has been updated independently in between getting and
        deleting, check-and-set is retried.
        """
        # Scenario: `/foo` already exists, but right after the `get` it gets
        # updated concurrently by another actor.
        self.model.create('/foo', 'delete-me', makepath=True)

        def get_foo(path):
            content, version = self.model.nodes[path]
            self.model.set(path, 'wibble', version=version)
            del self.model.get  # only run this behavior once
            return succeed((content, ZNodeStatStub(version)))

        self.model.get = get_foo

        def delete_or_update_func(original):
            if original == 'delete-me':
                return DELETE_NODE
            elif original == 'wibble':
                return original + '!'
        d = update_or_delete(self.model, '/foo', delete_or_update_func)
        self.assertEqual(self.successResultOf(d), 'wibble!')
        self.assertEqual(self.model.nodes, {'/foo': ('wibble!', 2)})
