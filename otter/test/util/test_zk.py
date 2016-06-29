"""Tests for otter.util.zk"""

from functools import partial

from characteristic import attributes

from effect import ComposedDispatcher, Effect, TypeDispatcher, sync_perform

from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.test.utils import test_dispatcher
from otter.util.zk import (
    AcquireLock, CreateOrSet, CreateOrSetLoopLimitReachedError,
    DeleteNode, GetChildren, GetChildrenWithStats,
    GetStat,
    get_zk_dispatcher,
    perform_create_or_set, perform_delete_node)


@attributes(['version'])
class ZNodeStatStub(object):
    """Like a :obj:`ZnodeStat`, but only supporting the data we need."""


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
        """Create a node."""
        assert makepath is True, "makepath must be True"
        if path in self.nodes:
            return fail(NodeExistsError("{} already exists".format(path)))
        self.nodes[path] = (content, 0)
        return succeed(path)

    def get(self, path):
        """Get content of the node, and stat info."""
        if path not in self.nodes:
            return fail(NoNodeError("{} does not exist".format(path)))
        content, version = self.nodes[path]
        return succeed((content, ZNodeStatStub(version=version)))

    def _check_version(self, path, version):
        if path not in self.nodes:
            return fail(NoNodeError("{} does not exist".format(path)))
        if version != -1:
            current_version = self.nodes[path][1]
            if current_version != version:
                return fail(BadVersionError(
                    "When operating on {}, version {} was specified by "
                    "version {} was found".format(path, version,
                                                  current_version)))

    def set(self, path, new_value, version=-1):
        """Set the content of a node."""
        check = self._check_version(path, version)
        if check is not None:
            return check
        current_version = self.nodes[path][1]
        new_stat = ZNodeStatStub(version=current_version + 1)
        self.nodes[path] = (new_value, new_stat.version)
        return succeed(new_stat)

    def delete(self, path, version=-1):
        """Delete a node."""
        check = self._check_version(path, version)
        if check is not None:
            return check
        del self.nodes[path]
        return succeed('delete return value')

    def exists(self, path):
        """Return a ZnodeStat for a node if it exists, otherwise None."""
        if path in self.nodes:
            return ZNodeStatStub(version=self.nodes[path][1])
        else:
            return None

    def Lock(self, path):
        return ZKLock(self, path)


class ZKLock(object):
    """
    Stub for :obj:`kazoo.recipe.lock.KazooLock`
    """
    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.acquired = False
        self.acquire_calls = {}

    def acquire(self, blocking=True, timeout=None):
        assert not self.acquired
        self.acquired = self.acquire_calls[(blocking, timeout)]
        return succeed(self.acquired)

    def release(self):
        self.acquired = False
        return succeed(None)


class CreateOrSetTests(SynchronousTestCase):
    """Tests for :func:`create_or_set`."""
    def setUp(self):
        self.model = ZKCrudModel()

    def _cos(self, path, content):
        eff = Effect(CreateOrSet(path=path, content=content))
        performer = partial(perform_create_or_set, self.model)
        dispatcher = TypeDispatcher({CreateOrSet: performer})
        return sync_perform(dispatcher, eff)

    def test_create(self):
        """Creates a node when it doesn't exist."""
        result = self._cos('/foo', 'bar')
        self.assertEqual(result, '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 0)})

    def test_update(self):
        """Uses `set` to update the node when it does exist."""
        self.model.create('/foo', 'initial', makepath=True)
        result = self._cos('/foo', 'bar')
        self.assertEqual(result, '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 1)})

    def test_node_disappears_during_update(self):
        """
        If `set` can't find the node (because it was unexpectedly deleted
        between the `create` and `set` calls), creation will be retried.
        """
        def hacked_set(path, value):
            self.model.delete('/foo')
            del self.model.set  # Only let this behavior run once
            return self.model.set(path, value)
        self.model.set = hacked_set

        self.model.create('/foo', 'initial', makepath=True)
        result = self._cos('/foo', 'bar')
        self.assertEqual(result, '/foo')
        # It must be at version 0 because it's a creation, whereas normally if
        # the node were being updated it'd be at version 1.
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 0)})

    def test_loop_limit(self):
        """
        performing a :obj:`CreateOrSet` will avoid infinitely looping in
        pathological cases, and eventually blow up with a
        :obj:`CreateOrSetLoopLimitReachedError`.
        """
        def hacked_set(path, value):
            return fail(NoNodeError())

        def hacked_create(path, content, makepath):
            return fail(NodeExistsError())

        self.model.set = hacked_set
        self.model.create = hacked_create

        exc = self.assertRaises(CreateOrSetLoopLimitReachedError,
                                self._cos, '/foo', 'bar')
        self.assertEqual(str(exc), '/foo')


class GetChildrenWithStatsTests(SynchronousTestCase):
    """Tests for :func:`get_children_with_stats`."""
    def setUp(self):
        # It'd be nice if we used the standard ZK CRUD model, but implementing
        # a tree of nodes supporting get_children is a pain
        class Model(object):
            pass
        self.model = Model()

    def _gcws(self, path):
        eff = Effect(GetChildrenWithStats(path))
        dispatcher = ComposedDispatcher([test_dispatcher(),
                                         get_zk_dispatcher(self.model)])
        return sync_perform(dispatcher, eff)

    def test_get_children_with_stats(self):
        """
        get_children_with_stats returns path of all children along with their
        ZnodeStat objects. Any children that disappear between ``get_children``
        and ``exists`` are not returned.
        """
        def exists(p):
            if p == '/path/foo':
                return succeed(ZNodeStatStub(version=0))
            if p == '/path/bar':
                return succeed(ZNodeStatStub(version=1))
            if p == '/path/baz':
                return succeed(None)
        self.model.get_children = {'/path': succeed(['foo', 'bar', 'baz'])}.get
        self.model.exists = exists

        result = self._gcws('/path')
        self.assertEqual(result,
                         [('foo', ZNodeStatStub(version=0)),
                          ('bar', ZNodeStatStub(version=1))])


class GetChildrenTests(SynchronousTestCase):
    """Tests for :obj:`GetChildren`."""

    def setUp(self):
        # It'd be nice if we used the standard ZK CRUD model, but implementing
        # a tree of nodes supporting get_children is a pain
        class Model(object):
            pass
        self.model = Model()

    def _gc(self, path):
        eff = Effect(GetChildren(path))
        dispatcher = get_zk_dispatcher(self.model)
        return sync_perform(dispatcher, eff)

    def test_get_children(self):
        """Returns children."""
        self.model.get_children = {'/path': succeed(['foo', 'bar', 'baz'])}.get

        result = self._gc('/path')
        self.assertEqual(result,
                         ['foo', 'bar', 'baz'])


class GetStatTests(SynchronousTestCase):
    def setUp(self):
        self.model = ZKCrudModel()

    def _gs(self, path):
        eff = Effect(GetStat(path))
        dispatcher = get_zk_dispatcher(self.model)
        return sync_perform(dispatcher, eff)

    def test_get_stat(self):
        """Returns the ZnodeStat when the node exists."""
        self.model.create('/foo/bar', content='foo', makepath=True)
        result = self._gs('/foo/bar')
        self.assertEqual(result, ZNodeStatStub(version=0))

    def test_get_stat_not_exists(self):
        """Returns None when no node exists."""
        result = self._gs('/foo/bar')
        self.assertEqual(result, None)


class DeleteTests(SynchronousTestCase):
    """Tests for :obj:`DeleteNode`."""
    def test_delete(self):
        model = ZKCrudModel()
        eff = Effect(DeleteNode(path='/foo', version=1))
        model.create('/foo', 'initial', makepath=True)
        model.set('/foo', 'bar')
        performer = partial(perform_delete_node, model)
        dispatcher = TypeDispatcher({DeleteNode: performer})
        result = sync_perform(dispatcher, eff)
        self.assertEqual(model.nodes, {})
        self.assertEqual(result, 'delete return value')


class AcquireLockTests(SynchronousTestCase):
    """Tests for :obj:`AcquireLock`."""
    def test_success(self):
        lock = ZKLock("client", "path")
        lock.acquire_calls[(True, 0.3)] = True
        eff = Effect(AcquireLock(lock, True, 0.3))
        dispatcher = get_zk_dispatcher("client")
        result = sync_perform(dispatcher, eff)
        self.assertIs(result, True)
