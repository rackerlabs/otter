"""Tests for otter.util.zk"""

from functools import partial

from characteristic import attributes

from effect import Effect, TypeDispatcher
from effect.twisted import perform

from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.util.zk import (
    Create,
    DeleteNode, GetChildren,
    perform_create, perform_delete_node,
    perform_get_children)


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

    def create(self, path, content='', makepath=False):
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


class CreateTests(SynchronousTestCase):
    """Tests for :func:`create_or_set`."""
    def setUp(self):
        self.model = ZKCrudModel()

    def _cos(self, path):
        eff = Effect(Create(path))
        performer = partial(perform_create, self.model)
        dispatcher = TypeDispatcher({Create: performer})
        return perform(dispatcher, eff)

    def test_create(self):
        """Creates a node when it doesn't exist."""
        d = self._cos('/foo')
        self.assertEqual(self.successResultOf(d), '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('', 0)})


class GetChildrenTests(SynchronousTestCase):
    """Tests for :obj:`GetChildren`."""
    def setUp(self):
        # It'd be nice if we used the standard ZK CRUD model, but implementing
        # a tree of nodes supporting get_children is a pain
        class Model(object):
            pass
        self.model = Model()

    def _gcws(self, path):
        eff = Effect(GetChildren(path))
        performer = partial(perform_get_children, self.model)
        dispatcher = TypeDispatcher({GetChildren: performer})
        return perform(dispatcher, eff)

    def test_get_children_with_stats(self):
        """
        get_children_with_stats returns path of all children along with their
        ZnodeStat objects. Any children that disappear between ``get_children``
        and ``exists`` are not returned.
        """
        self.model.get_children = {'/path': succeed(['foo', 'bar', 'baz'])}.get
        d = self._gcws('/path')
        self.assertEqual(self.successResultOf(d), ['foo', 'bar', 'baz'])


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
        self.assertEqual(self.successResultOf(d), 'delete return value')
