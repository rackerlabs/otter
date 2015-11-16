#!/usr/bin/env python

"""
Loads cql into Cassandra
"""
from __future__ import print_function

import argparse
import csv
import re
import sys

from cql.apivalues import ProgrammingError
from cql.connection import connect

from silverberg.client import CQLClient, ConsistencyLevel

from twisted.internet import task
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import clientFromString

from txeffect import perform

from otter.effect_dispatcher import get_working_cql_dispatcher
from otter.models.cass import CassScalingGroupCollection
from otter.test.resources import CQLGenerator
from otter.util.cqlbatch import batch


the_parser = argparse.ArgumentParser(description="Load data into Cassandra.")


the_parser.add_argument(
    'cql_dir', type=str, metavar='cql_dir',
    help='Directory containing *.cql files to merge and replace.')

the_parser.add_argument(
    '--migrate', '-m', type=str,
    choices=['webhook_migrate', 'webhook_index', 'insert_deleting_false',
             'set_desired'],
    help='Run a migration job')

the_parser.add_argument(
    "--desired-csv", dest="desired_csv",
    help=("CSV file containing three columns: tenant ID, group ID and new "
          "desired value. This is only necessary/valid for the `set_desired` "
          "migration."))

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
        print(e.message)
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
        print("Attempting to connect to {0}:{1}".format(args.host, args.port))
    try:
        connection = connect(args.host, args.port, cql_version='3.0.4')
    except Exception as e:
        print("CONNECTION ERROR: {0}".format(e.message))
        sys.exit(1)
    cursor = connection.cursor()

    # execute commands
    execute_commands(cursor, commands, args.verbose)

    if args.verbose > 0:
        print('\n----\n')
        print("Done.  Disconnecting.")

    cursor.close()
    connection.close()


def execute_commands(cursor, commands, verbose):
    """
    Execute commands
    """
    for command in commands:
        try:
            cursor.execute(command, {})
        except ProgrammingError as pe:
            # if somewhat verbose, then print(out all errors.)
            # if less verbose, print out only non-already-existing errors
            message = pe.message.lower()
            significant_error = (
                "already exist" not in message and
                "existing keyspace" not in message and
                "existing column" not in message and
                not re.search("index '.*' could not be found", message))

            if verbose > 1 or significant_error:
                print('\n----\n')
                print(command)
                print("{0}".format(pe.message.strip()))

            if significant_error:
                sys.exit(1)

        else:
            # extremely verbose - notify that command executed correctly.
            if args.verbose > 2:
                print('\n----\n')
                print(command)
                print("Ok.")


def webhook_index(reactor, conn, args):
    """
    Show webhook indexes that is not there table connection
    """
    store = CassScalingGroupCollection(None, None, 3)
    eff = store.get_webhook_index_only()
    return perform(get_working_cql_dispatcher(reactor, conn), eff)


def webhook_migrate(reactor, conn, args):
    """
    Migrate webhook indexes to table
    """
    store = CassScalingGroupCollection(None, None, 3)
    eff = store.get_webhook_index_only().on(store.add_webhook_keys)
    return perform(get_working_cql_dispatcher(reactor, conn), eff)


@inlineCallbacks
def insert_deleting_false(reactor, conn, args):
    """
    Insert false to all group's deleting column
    """
    store = CassScalingGroupCollection(conn, None, 3)
    groups = yield store.get_scaling_group_rows()
    query = (
        'INSERT INTO scaling_group ("tenantId", "groupId", deleting) '
        'VALUES (:tenantId{i}, :groupId{i}, false);')
    queries, params = [], {}
    for i, group in enumerate(groups):
        queries.append(query.format(i=i))
        params['tenantId{}'.format(i)] = group['tenantId']
        params['groupId{}'.format(i)] = group['groupId']
    yield conn.execute(batch(queries), params, ConsistencyLevel.ONE)
    returnValue(None)


@inlineCallbacks
def set_desired(reactor, conn, args):
    if not args.desired_csv:
        raise Exception("Please provide a --desired-csv")
    reader = csv.reader(open(args.desired_csv))

    query = (
        'UPDATE scaling_group SET desired=:desired{i} '
        'WHERE "tenantId"=:tenantId{i} AND "groupId"=:groupId{i}')
    queries, params = [], {}
    for i, (tenant_id, group_id, new_desired) in enumerate(reader):
        queries.append(query.format(i=i))
        params['tenantId{}'.format(i)] = tenant_id
        params['groupId{}'.format(i)] = group_id
        params['desired{}'.format(i)] = int(new_desired)
    yield conn.execute(batch(queries), params, ConsistencyLevel.ONE)
    returnValue(None)


def setup_connection(reactor, args):
    """
    Return Cassandra connection
    """
    return CQLClient(
        clientFromString(reactor, 'tcp:{}:{}'.format(args.host, args.port)),
        args.keyspace)


def run_migration(reactor, job, args):
    """ Run migration job """
    conn = setup_connection(reactor, args)
    d = globals()[job](reactor, conn, args)
    return d.addCallback(lambda _: conn.disconnect())


def run(args):
    if args.migrate:
        task.react(run_migration, (args.migrate, args))
    else:
        generate(args)


args = the_parser.parse_args()
run(args)
