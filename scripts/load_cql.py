#!/usr/bin/env python

"""
Loads cql into Cassandra
"""

import argparse
import sys

from cql.apivalues import ProgrammingError
from cql.connection import connect

from otter.test.resources import CQLGenerator


the_parser = argparse.ArgumentParser(description="Load data into Cassandra.")


the_parser.add_argument(
    'cql_dir', type=str, metavar='cql_dir',
    help='Directory containing *.cql files to merge and replace.')

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


def run(args):
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
        connection = connect(args.host, args.port, cql_version='3')
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
                "existing keyspace" not in message)

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


args = the_parser.parse_args()
run(args)
