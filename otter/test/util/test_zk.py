"""Tests for otter.util.zk"""

from kazoo.exceptions import BadVersionError, NoNodeError, NodeExistsError

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.util.zk import create_or_set


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
        check = self._check_version(path, version)
        if check is not None:
            return check
        current_version = self.nodes[path][1]
        new_stat = ZNodeStatStub(current_version + 1)
        self.nodes[path] = (new_value, new_stat.version)
        return succeed(new_stat)

    def delete(self, path, version=-1):
        check = self._check_version(path, version)
        if check is not None:
            return check
        del self.nodes[path]
        return succeed(None)


class CreateOrSetTests(SynchronousTestCase):
    def setUp(self):
        self.model = ZKCrudModel()

    def test_create(self):
        d = create_or_set(self.model, '/foo', 'bar')
        self.assertEqual(self.successResultOf(d), '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 0)})

    def test_update(self):
        self.model.create('/foo', 'initial', makepath=True)
        d = create_or_set(self.model, '/foo', 'bar')
        self.assertEqual(self.successResultOf(d), '/foo')
        self.assertEqual(self.model.nodes, {'/foo': ('bar', 1)})

    def test_node_disappears_during_update(self):
        1 / 0
