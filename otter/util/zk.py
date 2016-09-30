import time
import uuid

from functools import partial

import attr

from characteristic import attributes

from effect import (
    ComposedDispatcher, Constant, Delay, Effect, Func, TypeDispatcher, catch,
    parallel, sync_performer)
from effect.do import do, do_return

from kazoo.exceptions import LockTimeout, NoNodeError, NodeExistsError

import six

from twisted.internet.defer import maybeDeferred

from txeffect import deferred_performer, perform

from otter.util.deferredutils import catch_failure


CREATE_OR_SET_LOOP_LIMIT = 50
"""
A limit on the number of times we'll jump between trying to create a node
vs trying to set a node's contents in perform_create_or_set.
"""


@attr.s
class CreateNode(object):
    """
    Intent to create znode
    """
    path = attr.ib()
    value = attr.ib(default="")
    ephemeral = attr.ib(default=False)
    sequence = attr.ib(default=False)


@deferred_performer
def perform_create(kz_client, dispatcher, intent):
    """Perform :obj:`CreateNode`.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param CreateNode intent: the intent
    """
    return kz_client.create(
        intent.path, value=intent.value, ephemeral=intent.ephemeral,
        sequence=intent.sequence)


@attributes(['path', 'content'])
class CreateOrSet(object):
    """
    Create a node, or if the node already exists, set the content.

    Handles the case where a node gets deleted in between our attempt and
    creating and setting.
    """


class CreateOrSetLoopLimitReachedError(Exception):
    """
    Raised when the number of times trying to create a node in
    :func:`perform_create_or_set` has gone over
    :obj:`CREATE_OR_SET_LOOP_LIMIT`.
    """


@deferred_performer
def perform_create_or_set(kz_client, dispatcher, create_or_set):
    """
    Performer for :obj:`CreateOrSet`. Must be partialed with ``kz_client``.
    """
    path = create_or_set.path
    content = create_or_set.content

    def create(count):
        if count >= CREATE_OR_SET_LOOP_LIMIT:
            raise CreateOrSetLoopLimitReachedError(path)
        d = kz_client.create(path, content, makepath=True)
        d.addErrback(catch_failure(NodeExistsError,
                                   lambda f: set_content(count)))
        return d

    def set_content(count):
        d = kz_client.set(path, content)
        d.addErrback(catch_failure(NoNodeError,
                                   lambda f: create(count + 1)))
        return d.addCallback(lambda r: path)

    return create(0)


@attributes(['path'], apply_with_init=False)
class GetChildrenWithStats(object):
    """
    List children along with their stat information.

    Results in ``[(child_path, :obj:`ZnodeStat`)]``.
    """
    def __init__(self, path):
        self.path = path


@sync_performer
@do
def perform_get_children_with_stats(kz_client, dispatcher, intent):
    """
    Perform :obj:`GetChildrenWithStats`. Must be partialed with ``kz_client``.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param GetChildrenWithStats intent: the intent
    """
    path = intent.path
    children = yield Effect(GetChildren(path))
    stats = yield parallel(Effect(GetStat(path + '/' + p)) for p in children)
    yield do_return([
        c_and_s for c_and_s in zip(children, stats)
        if c_and_s[1] is not None])


@attributes(['path'], apply_with_init=False)
class GetChildren(object):
    """List children."""
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_children(kz_client, dispatcher, intent):
    """Perform a :obj:`GetChildren`."""
    return kz_client.get_children(intent.path)


@attributes(['path'], apply_with_init=False)
class GetStat(object):
    """
    Get the :obj:`ZnodeStat` of a ZK node, or None if the node does not exist.
    """
    def __init__(self, path):
        self.path = path


@deferred_performer
def perform_get_stat(kz_client, dispatcher, intent):
    """Perform a :obj:`GetStat`."""
    return kz_client.exists(intent.path)


@attributes(['path', 'version'])
class DeleteNode(object):
    """Delete a node."""


@deferred_performer
def perform_delete_node(kz_client, dispatcher, intent):
    """Perform :obj:`DeleteNode`.

    :param kz_client: txKazoo client
    :param dispatcher: dispatcher, supplied by perform
    :param DeleteNode intent: the intent
    """
    return kz_client.delete(intent.path, version=intent.version)


@attr.s
class GetNode(object):
    path = attr.ib(validator=attr.validators.instance_of(six.string_types))


@attr.s
class UpdateNode(object):
    path = attr.ib(validator=attr.validators.instance_of(six.string_types))
    value = attr.ib(validator=attr.validators.instance_of(six.binary_type))


def get_zk_dispatcher(kz_client):
    """Get a dispatcher that can support all of the ZooKeeper intents."""
    return TypeDispatcher({
        CreateNode: partial(perform_create, kz_client),
        CreateOrSet:
            partial(perform_create_or_set, kz_client),
        DeleteNode:
            partial(perform_delete_node, kz_client),
        GetChildrenWithStats:
            partial(perform_get_children_with_stats, kz_client),
        GetChildren:
            partial(perform_get_children, kz_client),
        GetStat:
            partial(perform_get_stat, kz_client)
    })


class PollingLock(object):
    """
    Zookeeper lock recipe that polls the children on interval basis instead
    of leaving a watch on previous child. It's supposed to replace
    :obj:`kazoo.recipe.lock.Lock` and has same signature and _similar_ behavior
    for ``acquire`` and ``release`` methods.
    """

    def __init__(self, dispatcher, path, identifier="", interval=0.1):
        self.dispatcher = dispatcher
        self.path = path
        self.identifier = identifier
        self._interval = interval
        # Child node described in
        # https://zookeeper.apache.org/doc/trunk/recipes.html#sc_recipes_Locks
        self._node = None

    def acquire(self, blocking=True, timeout=None):
        """
        Same as :meth:`kazoo.recipe.lock.Lock.acquire` except that this can be
        called again on an object that has been released. It will start fresh
        process to acquire the lock.
        """
        return perform(self.dispatcher, self.acquire_eff(blocking, timeout))

    @do
    def acquire_eff(self, blocking, timeout):
        """
        Effect implementation of ``acquire`` method.

        :return: ``Effect`` of ``bool``
        """
        try:
            # Before acquiring, lets delete any child node which may be
            # lingering from previous acquire. Ideally this should happen only
            # when acquire is called again before release. This shouldn't
            # happen this is called after release or after is_acquired returns
            # False. In any case, its the safest thing to do
            yield self.release_eff()
            try:
                yield Effect(CreateNode(self.path))
            except NodeExistsError:
                pass
            prefix = yield Effect(Func(uuid.uuid4))
            # TODO: https://github.com/rackerlabs/otter/issues/1926
            create_intent = CreateNode(
                "{}/{}".format(self.path, prefix),
                value=self.identifier, ephemeral=True, sequence=True)
            self._node = yield Effect(create_intent)
            acquired = yield self._acquire_loop(blocking, timeout)
            if not acquired:
                yield self.release_eff()
            yield do_return(acquired)
        except Exception as e:
            yield self.release_eff()
            raise e

    @do
    def _acquire_loop(self, blocking, timeout):
        acquired = yield self.is_acquired_eff()
        if acquired or not blocking:
            yield do_return(acquired)
        start = yield Effect(Func(time.time))
        while True:
            yield Effect(Delay(self._interval))
            if (yield self.is_acquired_eff()):
                yield do_return(True)
            if timeout is not None:
                now = yield Effect(Func(time.time))
                if now - start > timeout:
                    raise LockTimeout(
                        "Failed to acquire lock on {} in {} seconds".format(
                            self.path, now - start))

    def is_acquired(self):
        """
        Is the lock already acquired? This method does not exist in kazoo
        lock recipe and is a nice addition to it.

        :return: :obj:`Deferred` of ``bool``
        """
        return perform(self.dispatcher, self.is_acquired_eff())

    @do
    def is_acquired_eff(self):
        """
        Effect implementation of ``is_acquired``.

        :return: ``Effect`` of ``bool``
        """
        if self._node is None:
            yield do_return(False)
        children = yield Effect(GetChildren(self.path))
        if not children:
            yield do_return(False)
        # The last 10 characters are sequence number as per
        # https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html#Sequence+Nodes+--+Unique+Naming
        basename = self._node.rsplit("/")[-1]
        yield do_return(sorted(children, key=lambda c: c[-10:])[0] == basename)

    def release(self):
        """
        Same as :meth:`kazoo.recipe.lock.Lock.release`
        """
        return perform(self.dispatcher, self.release_eff())

    def release_eff(self):
        """
        Effect implementation of ``release``.

        :return: ``Effect`` of ``None``
        """
        def reset_node(_):
            self._node = None

        if self._node is not None:
            return Effect(DeleteNode(path=self._node, version=-1)).on(
                success=reset_node, error=catch(NoNodeError, reset_node))
        else:
            return Effect(Constant(None))


# Sentinet object representing the fact that eff passed in ``call_if_acquired``
# was not called
NOT_CALLED = object()


@do
def call_if_acquired(lock, eff):
    """
    Call ``eff`` if ``lock`` is acquired. If not, try to acquire the lock
    and call ``eff``. This function is different from
    :func:`otter.util.deferredutils.with_lock` where this does not release
    the lock after calling ``func``. Also it expects that lock may already be
    acquired.

    :param lock: Lock object from :obj:`TxKazooClient`
    :param eff: ``Effect`` to call if lock is/was acquired

    :return: (eff return, lock acquired bool) tuple. first element may be
        ``NOT_CALLED`` of eff was not called
    :rtype: ``Effect`` of ``bool``
    """
    if (yield lock.is_acquired_eff()):
        ret = yield eff
        yield do_return((ret, False))
    else:
        if (yield lock.acquire_eff(False, None)):
            ret = yield eff
            yield do_return((ret, True))
        else:
            yield do_return((NOT_CALLED, False))


def locked(lock, dispatcher, func, *args, **kwargs):
    """
    Deferred wrapper of :func:`call_if_acquired`. Return function that will
    call ``func`` if given ``lock`` is acquired. That function will return
    Deferred fired with (func return, lock acquired bool) tuple. First element
    may be ``NOT_CALLED`` of func was not called.

    Note: Signature change is one of the reasons why this is not decorator.

    :return: no-argument callable that wraps given ``func``
    """

    def check_and_call():

        class DoFunc(object):
            pass

        @deferred_performer
        def func_performer(d, i):
            return maybeDeferred(func, *args, **kwargs)

        comp_dispatcher = ComposedDispatcher([
            TypeDispatcher({DoFunc: func_performer}), dispatcher])
        return perform(
            comp_dispatcher,
            call_if_acquired(lock, Effect(DoFunc())))

    return check_and_call


def add_acquired_log(log, message, func):
    """
    Add log message if func returns the fact that lock is acquired. This
    function should be in conjunction with :func:`locked`.

    :return: no-argument callable that returns result of function wrapped
        in :func:`locked`
    """

    def log_acquired(r):
        result, acquired = r
        if acquired:
            log.msg(message)
        return result

    def f():
        return func().addCallback(log_acquired)

    return f


def locked_logged_func(dispatcher, path, log, message, func, *args, **kwargs):
    """
    Composition of :func:`locked` and :func:`add_acquired_log` function. The
    only extra thing this does is creating the lock.

    :return: (wrapped function, lock object) tuple
    """
    lock = PollingLock(dispatcher, path)
    f = locked(lock, dispatcher, func, *args, **kwargs)
    return add_acquired_log(log, message, f), lock


def create_health_check(lock):
    """
    Return health check function that captures whether the lock is acquired
    """

    def health_check():
        d = lock.is_acquired()
        return d.addCallback(lambda b: (True, {"has_lock": b}))

    return health_check
