"""Tests for otter.util.zk"""

from functools import partial

from characteristic import attributes

from effect import Effect, TypeDispatcher
from effect.twisted import perform

from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.util.zk import (
    CreateOrSet, DeleteNode, GetChildrenWithStats,
    perform_create_or_set, perform_delete_node,
    perform_get_children_with_stats)


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
        return succeed(None)


class CreateOrSetTests(SynchronousTestCase):
    """Tests for :func:`create_or_set`."""
    def setUp(self):
        self.model = ZKCrudModel()

    def _cos(self, path, content):
        eff = Effect(CreateOrSet(path=path, content=content))
        performer = partial(perform_create_or_set, self.model)
        dispatcher = TypeDispatcher({CreateOrSet: performer})
        return perform(dispatcher, eff)

    def test_create(self):
        """Creates a node when it doesn't exist."""
        d = self._cos('/foo', 'bar')
        self.assertEqual(self.successResultOf(d), '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 0)})

    def test_update(self):
        """Uses `set` to update the node when it does exist."""
        self.model.create('/foo', 'initial', makepath=True)
        d = self._cos('/foo', 'bar')
        self.assertEqual(self.successResultOf(d), '/foo')
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
        d = self._cos('/foo', 'bar')
        self.assertEqual(self.successResultOf(d), '/foo')
        # It must be at version 0 because it's a creation, whereas normally if
        # the node were being updated it'd be at version 1.
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 0)})


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
        performer = partial(perform_get_children_with_stats, self.model)
        dispatcher = TypeDispatcher({GetChildrenWithStats: performer})
        return perform(dispatcher, eff)

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

        d = self._gcws('/path')
        self.assertEqual(self.successResultOf(d),
                         [('foo', ZNodeStatStub(version=0)),
                          ('bar', ZNodeStatStub(version=1))])

class DeleteTests(SynchronousTestCase):
    """Tests for :obj:`DeleteNode`."""
    def test_delete(self):
        model = ZKCrudModel()
        eff = Effect(DeleteNode(path='/foo', version=1))
        model.create('/foo', 'initial', makepath=True)
        model.set('/foo', 'bar')
        performer = partial(perform_delete_node, model)
        dispatcher = TypeDispatcher({DeleteNode: performer})
        d = perform(dispatcher, eff)
        self.assertEqual(model.nodes, {})
        self.assertEqual(self.successResultOf(d), None)

        
