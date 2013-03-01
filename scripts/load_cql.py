"""
Loads cql into Cassandra
"""

import argparse

from otter.test.resources import CQLGenerator, RunningCassandraCluster


top_parser = argparse.ArgumentParser(description="Load data into Cassandra.")
subparsers = top_parser.add_subparsers(dest='command')

generate = subparsers.add_parser('generate', help='Generate CQL only')
execute = subparsers.add_parser('execute', help='Generate and execute CQL')


def add_args(the_parser):
    """
    Add arguments common to both subcommands
    """
    the_parser.add_argument('cql_dir', **{
        'type': str,
        'help': 'Directory containing *.cql files to merge and replace. '
    })

    the_parser.add_argument('keyspace', **{
        'metavar': 'keyspace',
        'type': str,
        'help': 'The name of the keyspace'
    })

    the_parser.add_argument('--replication', **{
        'type': int,
        'default': 1,
        'help': 'Replication factor to use if creating the keyspace.  Default: 1'
    })


add_args(generate)
add_args(execute)


execute.add_argument('what', **{
    'type': str,
    'choices': ['setup', 'teardown'],
    'help': 'What the CQL does'
})
execute.add_argument('--host', **{
    'type': str,
    'default': 'localhost',
    'help': ('If --execute is given, the host of the cluster to connect to. '
             'Default: localhost')
})
execute.add_argument('--port', **{
    'type': int,
    'default': 9160,
    'help': ('If --execute is given, the port of the cluster to connect to. '
             'Default: 9160')
})
generate.add_argument('outfile', **{
    'type': argparse.FileType('w'),
    'help': 'The output file to write the generated CQL to.'
})


def run(args):
    """
    Generate CQL and/or load it into a cassandra instance/cluster.
    """
    generator = CQLGenerator(args.cql_dir)

    if args.command == 'generate':
        generator.generate_cql(args.keyspace,
                               replication_factor=args.replication,
                               outfile=args.outfile)
    else:
        cluster = RunningCassandraCluster(**{
            'host': args.host, 'port': args.port,
            '{0}_cql'.format(args.what): generator.generate_cql})
        execute = getattr(cluster, '{0}_keyspace'.format(args.what))
        execute(args.keyspace, replication_factor=args.replication)


args = top_parser.parse_args()
run(args)
