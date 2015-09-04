"""
A set of helpers for writing trial tests
"""
import json
import os
from datetime import datetime, timedelta

from testtools.matchers import (
    AfterPreprocessing,
    AllMatch,
    ContainsDict,
    Equals,
    MatchesAll)

from twisted.internet import reactor

from twisted.internet.defer import (
    Deferred, gatherResults, inlineCallbacks, returnValue)

from twisted.python.log import addObserver, removeObserver

from twisted.web.client import HTTPConnectionPool

from otter import auth

from otter.integration.lib.autoscale import (
    HasActive,
    ScalingGroup,
    ScalingPolicy,
    create_scaling_group_dict
)

from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer, ContainsAllIPs)

from otter.integration.lib.identity import IdentityV2

from otter.integration.lib.nova import (
    create_server,
    delete_servers,
    wait_for_servers
)

from otter.log import log

from otter.log.formatters import (
    ErrorFormattingWrapper,
    LoggingEncoder,
    PEP3101FormattingWrapper,
    StreamObserverWrapper,
)

from otter.util.logging_treq import LoggingTreq


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']
scheduler_interval = float(os.environ.get("AS_SCHEDULER_INTERVAL", "10"))
otter_build_timeout = float(os.environ.get("AS_BUILD_TIMEOUT_SECONDS", "30"))
convergence_interval = float(os.environ.get("AS_CONVERGENCE_INTERVAL", "10"))

# Get vs dict lookup because it will return None if not found,
# not throw an exception.  None is a valid value for convergence_tenant.
convergence_tenant = os.environ.get('AS_CONVERGENCE_TENANT')
otter_key = os.environ.get('AS_AUTOSCALE_SC_KEY', 'autoscale')
otter_local_url = os.environ.get('AS_AUTOSCALE_LOCAL_URL')
nova_key = os.environ.get('AS_NOVA_SC_KEY', 'cloudServersOpenStack')
clb_key = os.environ.get('AS_CLB_SC_KEY', 'cloudLoadBalancers')

# these are the service names for mimic control planes
mimic_nova_key = os.environ.get("MIMICNOVA_SC_KEY", 'cloudServersBehavior')
mimic_clb_key = os.environ.get("MIMICCLB_SC_KEY", 'cloudLoadBalancerControl')


def get_identity(pool, username=username, password=password,
                 convergence_tenant=convergence_tenant):
    """
    Return an identity object based on the envirnment variables
    """
    return IdentityV2(
        auth=auth, username=username, password=password,
        endpoint=endpoint, pool=pool,
        convergence_tenant_override=convergence_tenant,
    )


def not_mimic():
    """
    Return True unless the environment variable AS_USING_MIMIC is set to
    something truthy.
    """
    return not bool(os.environ.get("AS_USING_MIMIC", False))


def get_resource_mapping():
    """
    Get resource mapping based on the environment settings
    """
    res = {'nova': (nova_key,), 'loadbalancers': (clb_key,)}
    if otter_local_url is not None:
        res['otter'] = ("badkey", otter_local_url)
    else:
        res['otter'] = (otter_key,)
    if not not_mimic():
        res['mimic_nova'] = (mimic_nova_key,)
        res['mimic_clb'] = (mimic_clb_key,)
    return res


def filter_logs(observer):
    """
    Filter out logs like
    "Starting factory <twisted.web.client_HTTP11ClientFactory".
    """
    def emit(eventdict):
        if ('message' not in eventdict or
                all([not m.startswith("Starting factory") and
                     not m.startswith("Stopping factory")
                     for m in eventdict['message']])):
            observer(eventdict)
    return emit


def pretty_print_logs(observer):
    """
    A log observer formatter for test logs.  Prints log messages like::

        MESSAGE
        {
            rest of JSON dict
        }

        --------

        MESSAGE
        {
            rest of JSON dict
        }

        ...
    """
    def emit(eventdict):
        if 'message' in eventdict:
            message = ''.join(eventdict.pop('message'))
        observer({'message': "\n".join(
            ["", message, json.dumps(eventdict, cls=LoggingEncoder, indent=2),
             "", "-" * 8]
        )})
    return emit


def copying_wrapper(observer):
    """
    An observer that copies the event-dict, so if there is more than one
    observer chain that mutates events, we don't get any errors.
    """
    def emit(event_dict):
        return observer(event_dict.copy())
    return emit


def setup_test_log_observer(testcase):
    """
    Create a log observer that writes a particular test's logs to a temporary
    file for the duration of the test.  Also cleans up the observer and the
    temp file object after the test is over.
    """
    logfile = open("{0}.log".format(testcase.id()), 'ab')
    observer = copying_wrapper(
        PEP3101FormattingWrapper(
            ErrorFormattingWrapper(
                filter_logs(
                    pretty_print_logs(
                        StreamObserverWrapper(logfile))))))
    addObserver(observer)
    testcase.addCleanup(removeObserver, observer)
    testcase.addCleanup(logfile.close)


def get_utcstr_from_now(seconds):
    """ Get UTC timestamp from now in ISO 8601 format """
    return "{}Z".format(
        (datetime.utcnow() + timedelta(seconds=seconds)).isoformat())


class TestHelper(object):
    """
    A helper class that contains useful functions for actual test cases.  This
    also creates a number of CLB that are required.
    """
    def __init__(self, test_case, num_clbs=0):
        """
        Set up the test case, HTTP pool, identity, and cleanup.
        """
        setup_test_log_observer(test_case)
        self.test_case = test_case
        self.pool = HTTPConnectionPool(reactor, False)
        self.treq = LoggingTreq(log=log, log_response=True)
        self.test_case.addCleanup(self.pool.closeCachedConnections)

        self.clbs = [CloudLoadBalancer(pool=self.pool, treq=self.treq)
                     for _ in range(num_clbs)]

    def create_group(self, **kwargs):
        """
        :return: a tuple of the scaling group with (the helper's pool) and
            the server name prefix used for the scaling group.
        """
        if self.clbs:
            # allow us to override the CLB setup
            kwargs.setdefault(
                'use_lbs',
                [clb.scaling_group_spec() for clb in self.clbs])

        kwargs.setdefault("image_ref", image_ref)
        kwargs.setdefault("flavor_ref", flavor_ref)
        kwargs.setdefault("min_entities", 0)

        server_name_prefix = "{}-{}".format(
            random_string(), reactor.seconds())
        if "server_name_prefix" in kwargs:
            server_name_prefix = "{}-{}".format(kwargs['server_name_prefix'],
                                                server_name_prefix)
        kwargs['server_name_prefix'] = server_name_prefix

        return (
            ScalingGroup(
                group_config=create_scaling_group_dict(**kwargs),
                treq=self.treq,
                pool=self.pool),
            server_name_prefix)

    @inlineCallbacks
    def start_group_and_wait(self, group, rcs, desired=None):
        """
        Start a group, and if desired is supplied, creates and executes a
        policy that scales to that number.  This would be used for example
        if we wanted to scale to the max of a group, but did not want the min
        to be equal to the max.

        This also waits for the desired number of servers to be reached - that
        would be desired if provided, or the min if not provided.

        :param TestResources rcs: An instance of
            :class:`otter.integration.lib.resources.TestResources`
        :param ScalingGroup group: An instance of
            :class:`otter.integration.lib.autoscale.ScalingGroup` to start -
            this group should not have been started already.
        :param int desired: A desired number to scale to.
        """
        yield group.start(rcs, self.test_case)
        if desired is not None:
            p = ScalingPolicy(set_to=desired, scaling_group=group)
            yield p.start(rcs, self.test_case)
            yield p.execute(rcs)

        if desired is None:
            desired = group.group_config['groupConfiguration'].get(
                'minEntities', 0)

        yield group.wait_for_state(
            rcs,
            MatchesAll(HasActive(desired),
                       ContainsDict({'pendingCapacity': Equals(0),
                                     'desiredCapacity': Equals(desired)})),
            timeout=600)

        if self.clbs:
            ips = yield group.get_servicenet_ips(rcs)
            yield gatherResults([
                clb.wait_for_nodes(
                    rcs, ContainsAllIPs(ips.values()), timeout=600)
                for clb in self.clbs])

        returnValue(rcs)

    @inlineCallbacks
    def create_servers(self, rcs, num, wait_for=None):
        """
        Create some number of servers using just Nova, and wait until they
        are active.  This uses the same default server arguments as
        `create_group`.

        :param TestResources rcs: An instance of
            :class:`otter.integration.lib.resources.TestResources`
        :param int num: The number of servers to create.
        :param wait_for: What state to wait for for those servers - by default,
            it waits just for them to be active

        :return: an iterable of server details JSON of the created servers.
        """
        as_args = create_scaling_group_dict(
            image_ref=image_ref,
            flavor_ref=flavor_ref)
        server_args = as_args['launchConfiguration']['args']
        server_args['server']['name'] = "autogenerated-non-as-test-server"

        if wait_for is None:
            wait_for = ContainsDict({'status': Equals("ACTIVE")})

        server_ids = yield gatherResults([
            create_server(rcs, self.pool, server_args) for _ in range(num)])

        self.test_case.addCleanup(delete_servers, server_ids, rcs, self.pool)

        servers = yield wait_for_servers(
            rcs,
            self.pool,
            # The list of active servers' ids has the created server ids
            AfterPreprocessing(
                lambda servers: [s for s in servers if s['id'] in server_ids],
                AllMatch(wait_for)
            )
        )

        returnValue(
            [server for server in servers if server['id'] in server_ids])

    @inlineCallbacks
    def assert_group_state(self, group, matcher):
        """
        Assert state of group conforms to the matcher
        """
        resp, state = yield group.get_scaling_group_state(self.test_case.rcs,
                                                          [200])
        self.test_case.assertIsNone(matcher.match(state["group"]))


def tag(*tags):
    """
    Decorator that adds tags to a function by setting the property "tags".

    This should be added upstream to Twisted trial.
    """
    def decorate(function):
        function.tags = tags
        return function
    return decorate


def skip_me(reason):
    """
    Decorator that skips a test method or test class by setting the property
    "skip".  This decorator is not named "skip", because setting "skip" on a
    module skips the whole test module.

    This should be added upstream to Twisted trial.
    """
    def decorate(function):
        function.skip = reason
        return function
    return decorate


def skip_if(predicate, reason):
    """
    Decorator that skips a test method or test class by setting the property
    "skip", and only if the provided predicate evaluates to True.
    """
    if predicate():
        return skip_me(reason)
    return lambda f: f


def copy_test_methods(from_class, to_class, filter_and_change=None):
    """
    Copy test methods (methods that start with `test_*`) from ``from_class`` to
    ``to_class``.  If a decorator is provided, the test method on the
    ``to_class`` will first be decorated before being set.

    :param class from_class: The test case to copy from
    :param class to_class: The test case to copy to
    :param callable filter_and_change: A function that takes a test name
        and test method, and returns a tuple of `(name, method)`
        if the test method should be copied. None else.  This allows the
        method name to change, the method to be decorated and/or skipped.
    """
    for name, attr in from_class.__dict__.items():
        if name.startswith('test_') and callable(attr):
            if filter_and_change is not None:
                filtered = filter_and_change(name, attr)
                if filtered is not None:
                    setattr(to_class, *filtered)
            else:
                setattr(to_class, name, attr)


def random_string(byte_len=4):
    """
    Generate a random string of the ``byte_len``.
    The string will be 2 * ``byte_len`` in length.
    """
    return os.urandom(byte_len).encode('hex')


def sleep(reactor, seconds):
    """
    Sleep for given seconds
    """
    d = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d
