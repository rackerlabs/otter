from __future__ import print_function

from functools import partial
from urllib import urlencode
import sys
import json

from twisted.internet import task, defer
from twisted.internet.endpoints import clientFromString

import treq

from silverberg.client import ConsistencyLevel
from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import groupby, filter, map
from toolz.functoolz import compose

from otter.util.http import append_segments, check_success, headers
from otter.auth import RetryingAuthenticator, ImpersonatingAuthenticator
from otter.log import log as otter_log
from otter.util.retry import retry, retry_times, exponential_backoff_interval

# TODO: I hate including this!
from otter.worker.launch_server_v1 import public_endpoint_url


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


@defer.inlineCallbacks
def get_all_server_details(reactor, tenant_id, authenticator, service_name, region, limit=100):
    """
    Return all servers of a tenant
    TODO: service_name is possibly internal to this function but I don't want to pass config here?
    NOTE: This really screams to be a independent txcloud-type API
    """
    token, catalog = yield authenticator.authenticate_tenant(tenant_id, log=otter_log)
    endpoint = public_endpoint_url(catalog, service_name, region)
    url = append_segments(endpoint, 'servers', 'detail')
    query = {'limit': limit}

    def fetch(url, headers):
        d = treq.get(url, headers=headers)
        d.addCallback(check_success, [200])
        d.addCallback(treq.json_content)
        return d

    all_servers = []
    while True:
        d = retry(partial(fetch, '{}?{}'.format(url, urlencode(query)), headers(token)),
                  can_retry=retry_times(5),
                  next_interval=exponential_backoff_interval(2), clock=reactor)
        servers = (yield d)['servers']
        all_servers.extend(servers)
        if len(servers) < limit:
            break
        query.update({'marker': servers[-1]['id']})

    defer.returnValue(all_servers)


def get_scaling_group_servers(reactor, tenant_id, authenticator, service_name, region):
    """
    Return tenant's servers that belong to a scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed
    """

    def group_id(server_details):
        m = server_details.get('metadata', {})
        return m.get('rax:auto_scaling_group_id', 'nogroup')

    def del_nogroup(grouped_servers):
        if 'nogroup' in grouped_servers:
            del grouped_servers['nogroup']
        return grouped_servers

    valid_statuses = ('ACTIVE', 'BUILD', 'HARD_REBOOT', 'MIGRATION', 'PASSWORD',
                      'RESIZE', 'REVERT_RESIZE', 'VERIFY_RESIZE')

    d = get_all_server_details(reactor, tenant_id, authenticator, service_name, region)
    # filter out invalid servers
    d.addCallback(filter(lambda s: s['status'] in valid_statuses))
    # group based on scaling_group_id
    d.addCallback(groupby(group_id))
    # remove servers not belonging to any group
    d.addCallback(del_nogroup)
    return d


def get_tenant_metrics(tenant_id, scaling_groups, servers):
    """
    Get tenant's metrics

    :param ``dict`` scaling_groups: Tenant's scaling groups from CASS
    :param ``dict`` servers: Servers from Nova grouped based on scaling group ID
    """


def process_tenant_groups(scaling_groups):
    """
    Process tenant's groups by collecting the real servers in a group and returning
    the total desired and total actual
    """


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

    total_desired = 0
    total_actual = [0]

    tenanted_groups = yield get_scaling_groups(reactor, client)
    print('got tenants', len(tenanted_groups))

    def calc_tenant_actual(tenant_id):
        d = get_scaling_group_servers(
            reactor, tenant_id, authenticator, config['services']['nova'], config['region'])
        d.addCallback(compose(sum, map(len), lambda servers: servers.itervalues()))
        return d

    def incr_total_actual(actual):
        total_actual[0] += actual
        print('total actual till now', total_actual[0])

    # TODO: Use cooperator instead
    sem = defer.DeferredSemaphore(10)
    defs = []
    for tenant_id, groups in tenanted_groups.iteritems():
        total_desired += sum([group['desired'] for group in groups])
        print('total desired till now', total_desired)
        d = sem.run(calc_tenant_actual, tenant_id)
        d.addCallback(incr_total_actual)
        defs.append(d)

    yield defer.gatherResults(defs)
    print('total desired: {}, total actual: {}'.format(total_desired, total_actual[0]))
    yield client.disconnect()


if __name__ == '__main__':
    config = json.load(open(sys.argv[1]))
    config['services'] = {'nova': 'cloudServersOpenStack'}
    task.react(main, (config, ))
