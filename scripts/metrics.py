"""
Script to collect metrics (total desired, actual and pending) from a DC
"""

from __future__ import print_function

from functools import partial
import sys
import json
from collections import namedtuple

from twisted.internet import task, defer
from twisted.internet.endpoints import clientFromString

from silverberg.client import ConsistencyLevel
from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import groupby, filter
from toolz.functoolz import compose

from otter.auth import RetryingAuthenticator, ImpersonatingAuthenticator
from otter.convergence import get_scaling_group_servers


@defer.inlineCallbacks
def get_scaling_groups(reactor, client, batch_size=100):
    """
    Return scaling groups grouped based on tenantId as
    {tenantId: list of groups} where each group is a ``dict`` that has
    'tenantId', 'groupId', 'desired', 'active' and 'pending' properties
    """
    # TODO: Currently returning all groups as one giant list for now. Will try to use Twisted tubes
    # to do streaming later
    query = ('SELECT "tenantId", "groupId", desired, active, pending FROM scaling_group '
             '{where} LIMIT :limit;')
    where_key = 'WHERE "tenantId"=:tenantId AND "groupId">:groupId'
    where_token = 'WHERE token("tenantId") > token(:tenantId)'

    # setup function that removes groups not having desired and groups them together
    # TODO: Better name than gfilter?
    gfilter = compose(groupby(lambda g: g['tenantId']),
                      filter(lambda g: g['desired'] is not None))

    batch = yield client.execute(query.format(where=''),
                                 {'limit': batch_size}, ConsistencyLevel.ONE)
    if len(batch) < batch_size:
        defer.returnValue(gfilter(batch))

    groups = batch
    while batch != []:
        # get all groups of tenantId
        tenantId = batch[-1]['tenantId']
        while len(batch) == batch_size:
            batch = yield client.execute(query.format(where=where_key),
                                         {'limit': batch_size, 'tenantId': tenantId,
                                          'groupId': batch[-1]['groupId']},
                                         ConsistencyLevel.ONE)
            groups.extend(batch)
        # Get next 'tenantId' rows using token
        batch = yield client.execute(query.format(where=where_token),
                                     {'limit': batch_size, 'tenantId': tenantId},
                                     ConsistencyLevel.ONE)
        groups.extend(batch)
    defer.returnValue(gfilter(groups))


GroupMetrics = namedtuple('GroupMetrics', 'tenant_id group_id desired actual')


def get_tenant_metrics(tenant_id, scaling_groups, servers):
    """
    Get tenant's metrics

    :param ``list`` of ``dict`` scaling_groups: Tenant's scaling groups from CASS
    :param ``dict`` servers: Servers from Nova grouped based on scaling group ID
    :return: ``list`` of (tenantId, groupId, desired, actual) GroupMetrics namedtuples
    """
    print('processing tenant {} with groups {} and servers {}'.format(
        tenant_id, len(scaling_groups), len(servers)))
    return [GroupMetrics(tenant_id, g['groupId'], g['desired'],
                         len(servers.get(g['groupId'], {})))
            for g in scaling_groups]


def get_authenticator(reactor, identity):
    """
    Return authenticator based on identity config
    """
    return RetryingAuthenticator(
        reactor,
        ImpersonatingAuthenticator(
            identity['username'],
            identity['password'],
            identity['url'],
            identity['admin_url']))


def connect_cass_servers(reactor, config):
    """
    Connect to Cassandra servers and return the connection
    """
    seed_endpoints = [clientFromString(reactor, str(host)) for host in config['seed_hosts']]
    return RoundRobinCassandraCluster(seed_endpoints, config['keyspace'], disconnect_on_cancel=True)


@defer.inlineCallbacks
def main(reactor, config):
    """
    Start collecting the metrics
    """
    client = connect_cass_servers(reactor, config['cassandra'])
    authenticator = get_authenticator(reactor, config['identity'])

    tenanted_groups = yield get_scaling_groups(reactor, client)
    print('got tenants', len(tenanted_groups))

    # TODO: Use cooperator instead
    sem = defer.DeferredSemaphore(10)
    defs = []
    all_groups = []
    for tenant_id, groups in tenanted_groups.iteritems():
        d = sem.run(
            get_scaling_group_servers, tenant_id, authenticator,
            config['services']['nova'], config['region'], clock=reactor)
        d.addCallback(partial(get_tenant_metrics, tenant_id, groups))
        d.addCallback(all_groups.extend)
        defs.append(d)

    yield defer.gatherResults(defs)
    total_desired = sum([g.desired for g in all_groups])
    total_actual = sum([g.actual for g in all_groups])
    print('total desired: {}, total actual: {}'.format(total_desired, total_actual))

    sorted_groups = sorted(all_groups, key=lambda g: abs(g.desired - g.actual), reverse=True)
    print('groups sorted as per divergence', *sorted_groups, sep='\n')

    yield client.disconnect()


if __name__ == '__main__':
    config = json.load(open(sys.argv[1]))
    config['services'] = {'nova': 'cloudServersOpenStack'}
    task.react(main, (config, ))
