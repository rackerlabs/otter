#!/usr/bin/env python

"""
Gather the current statistics on what's in the database
"""

import argparse
import sys

from cql.apivalues import ProgrammingError
from cql.connection import connect

the_parser = argparse.ArgumentParser(description="Get basic stats on usage of otter")

the_parser.add_argument(
    '--keyspace', type=str, default='otter',
    help='The name of the keyspace.  Default: otter')

the_parser.add_argument(
    '--host', type=str, default='localhost',
    help='The host of the cluster to connect to. Default: localhost')

the_parser.add_argument(
    '--port', type=int, default=9160,
    help='The port of the cluster to connect to. Default: 9160')

the_parser.add_argument(
    '--verbose', '-v', action='count', default=0, help="How verbose to be")


def run(args):
    """
    Run a set of simple canned queries against the DB
    """
    commands = [("use otter;", False, ""),
                ("SELECT COUNT(*) FROM scaling_config WHERE deleted=false;", True,
                 "Number of scaling groups: {0}"),
                ("SELECT COUNT(*) FROM launch_config WHERE deleted=false;", True,
                 "Number of launch configs (should be same as above): {0}"),
                ("SELECT COUNT(*) FROM group_state WHERE deleted=false;", True,
                 "Number of group states (should be same as above): {0}"),
                ("SELECT COUNT(*) FROM scaling_policies WHERE deleted=false;", True,
                 "Number of scaling policies: {0}"),
                ("SELECT COUNT(*) FROM policy_webhooks WHERE deleted=false;", True,
                 "Number of webhooks: {0}"),
                ]

    # connect
    if args.verbose > 0:
        print "Attempting to connect to {0}:{1}".format(args.host, args.port)
    try:
        connection = connect(args.host, args.port, cql_version='3')
    except Exception as e:
        print "CONNECTION ERROR: {0}".format(e.message)
        sys.exit(1)

    cursor = connection.cursor()

    for command, displayResults, label in commands:
        try:
            cursor.execute(command, {})
            if displayResults:
                print label.format(cursor.fetchone()[0])
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
