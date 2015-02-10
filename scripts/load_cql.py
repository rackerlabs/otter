#!/usr/bin/env python

"""
Loads cql into Cassandra
"""

import argparse
from functools import partial
import sys
import re

from cql.apivalues import ProgrammingError
from cql.connection import connect

# from cassandra.cluster import Cluster

from effect import (
    ComposedDispatcher,
    Effect,
    ParallelEffects,
    TypeDispatcher,
    base_dispatcher,
    parallel,
    perform,
    sync_performer
)

from pyrsistent import freeze

from silverberg.client import ConsistencyLevel

from toolz.dicttoolz import keymap

from otter.models.cass import CQLQueryExecute
from otter.test.resources import CQLGenerator
from otter.util.cqlbatch import batch


the_parser = argparse.ArgumentParser(description="Load data into Cassandra.")


the_parser.add_argument(
    'cql_dir', type=str, metavar='cql_dir',
    help='Directory containing *.cql files to merge and replace.')

the_parser.add_argument(
    '--webhook-migrate', action='store_false',
    help='Migrate webhook indexes to table')

the_parser.add_argument(
    '--keyspace', type=str, default='otter',
    help='The name of the keyspace.  Default: otter')

the_parser.add_argument(
    '--replication', type=int, default=1,
    help='Replication factor to use if creating the keyspace.  Default: 1')

the_parser.add_argument(
    '--ban-unsafe', action='store_true',
    help=('Whether to check for unsafe instructions ("alter", "drop", '
          '"truncate", and "delete", currently)'))

the_parser.add_argument(
    '--dry-run', action='store_true',
    help="If this option is passed, nothing actually gets loaded into cassandra.")

the_parser.add_argument(
    '--host', type=str, default='localhost',
    help='The host of the cluster to connect to. Default: localhost')

the_parser.add_argument(
    '--port', type=int, default=9160,
    help='The port of the cluster to connect to. Default: 9160')

the_parser.add_argument(
    '--outfile', type=argparse.FileType('w'),
    help=('The output file to write the generated CQL to.  If none is '
          'given, no file will be written to.'))

the_parser.add_argument(
    '--verbose', '-v', action='count', default=0, help="How verbose to be")


def generate(args):
    """
    Generate CQL and/or load it into a cassandra instance/cluster.
    """
    try:
        generator = CQLGenerator(args.cql_dir, safe_only=args.ban_unsafe)
    except Exception as e:
        print e.message
        sys.exit(1)

    cql = generator.generate_cql(
        keyspace_name=args.keyspace,
        replication_factor=args.replication,
        outfile=args.outfile)

    if args.dry_run:
        return

    # filter out comments, to make debugging easier
    cql = "\n".join(
        [line for line in cql.split('\n')
         if line.strip() and not line.strip().startswith('--')])

    # no blank lines or pointless whitespace
    commands = [x.strip() for x in cql.split(';') if x.strip()]

    # connect
    if args.verbose > 0:
        print "Attempting to connect to {0}:{1}".format(args.host, args.port)
    try:
        connection = connect(args.host, args.port, cql_version='3.0.4')
    except Exception as e:
        print "CONNECTION ERROR: {0}".format(e.message)
        sys.exit(1)

    cursor = connection.cursor()

    for command in commands:
        try:
            cursor.execute(command, {})
        except ProgrammingError as pe:
            # if somewhat verbose, then print out all errors.
            # if less verbose, print out only non-already-existing errors
            message = pe.message.lower()
            significant_error = (
                "already exist" not in message and
                "existing keyspace" not in message and
                "existing column" not in message and
                not re.search("index '.*' could not be found", message))

            if args.verbose > 1 or significant_error:
                print '\n----\n'
                print command
                print "{0}".format(pe.message.strip())

            if significant_error:
                sys.exit(1)

        else:
            # extremely verbose - notify that command executed correctly.
            if args.verbose > 2:
                print '\n----\n'
                print command
                print "Ok."

    if args.verbose > 0:
        print '\n----\n'
        print "Done.  Disconnecting."

    cursor.close()
    connection.close()


@sync_performer
def perform_query_sync(session, dispatcher, intent):
    query = re.sub(r':(\w+)', r'%(\1)s', intent.query)
    if intent.consistency_level == ConsistencyLevel.ONE:
        return session.execute(query, intent.params)
    else:
        return session.execute(
            SimpleStatement(query, consistency_level=intent.consistency_level),
            intent.params)


@sync_performer
def perform_serial(disp, intent):
    return map(partial(perform, disp), intent.effects)


def get_dispatcher(session):
    return ComposedDispatcher([
        base_dispatcher,
        TypeDispatcher({
            CQLQueryExecute: partial(perform_query_sync, session),
            ParallelEffects: perform_serial
        })
    ])


def get_webhook_index_only():
    """
    Get webhook info that is there in webhook index but is not there in
    webhook_keys table
    """
    query = 'SELECT "tenantId", "groupId", "policyId", "webhookKey" FROM {cf}'
    eff = parallel(
        [CQLQueryExecute(query=query.format(cf='policy_webhooks'), params={},
                         consistency_level=ConsistencyLevel.ONE),
         CQLQueryExecute(query=query.format(cf='webhook_keys'), params={},
                         consistency_level=ConsistencyLevel.ONE)])
    return eff.on(
        lambda (webhooks, wkeys): set(freeze(webhooks)) - set(freeze(wkeys)))


def add_webhook_keys(webhook_keys):
    """
    Add webhook keys to webhook_keys table
    """
    query = (
        'INSERT INTO {cf} "tenantId", "groupId", "policyId", "webhookKey"'
        'VALUES (:tenantId{i}, :groupId{i}, :policyId{i}, :webhookKey{i})')
    stmts = []
    data = {}
    for i, wkey in enumerate(webhook_keys):
        data.update(keymap(lambda k: k + str(i), wkey))
        stmts.append(query.format(cf='webhook_keys', i=i))
    return Effect(
        CQLQueryExecute(query=batch(stmts), params=data,
                        consistency_level=ConsistencyLevel.ONE))


def webhook_migrate():
    """
    Migrate webhook indexes to table
    """
    return get_webhook_index_only().on(add_webhook_keys)


def setup_session(args):
#     cluster = Cluster([args.host], port=args.port)
#     return cluster.connect(args.keyspace)
    pass


def run(args):
    if args.webhook_migrate:
        eff = webhook_migrate()
        perform(get_dispatcher(setup_session(args)), eff)
    else:
        generate(args)

args = the_parser.parse_args()
run(args)
