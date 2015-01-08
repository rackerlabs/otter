"""
Code to load keyspaces and data into a running Cassandra cluster.

Uses the python CQL driver, becuase silverberg doesn't yet support connecting
without a defined keyspace.
"""
import json
import os
import re

from cStringIO import StringIO
from glob import glob


def simple_create_keyspace(keyspace_name, replication_dict=None):
    """Given a keyspace name, produce the CQL3 statement that creates it.

    No schema set-up is done.  Uses a simple replication strategy and
    a replication factor of 1.

    :param keyspace_name: what the name of the keyspace is to create
    :type keyspace_name: ``str``

    """
    replication_dict = replication_dict or {
        'class': 'SimpleStrategy',
        'replication_factor': '1'
    }
    return "CREATE KEYSPACE {name} WITH replication = {replication}".format(
        name=keyspace_name, replication=json.dumps(replication_dict))


def simple_drop_keyspace(keyspace_name):
    """
    Given a keyspace name, produce keyspace dropping CQL (version 3 CQL).  No
    other cleanup is done.

    :param keyspace_name: what the name of the keyspace is to drop
    :type keyspace_name: ``str``
    """
    return "DROP KEYSPACE {name}".format(name=keyspace_name)


_drop_regex = re.compile('^\s*(alter|drop|truncate|delete)\s', re.I | re.M)


class CQLGenerator(object):

    """Combines CQL files in a directory into one SQL statement, in order."""

    def __init__(self, directory, safe_only=True):
        """
        Initialize :class:`CQLGenerator`.

        :param directory: directory in which all the cql files are that should
            be merged (the files should be named such that sorting them
            alphabetically will list them in the right order)
        :type directory: ``str``

        :param safe_only: whether or not to ban drop statements
        :type safe_only: ``bool``
        """
        files = sorted(glob(os.path.join(directory, '*.cql')))
        text = StringIO()
        for cql_file in files:
            with open(cql_file) as fd:
                content = fd.read()
                if safe_only:
                    unsafe = _drop_regex.search(content)
                    if unsafe:
                        unsafe = unsafe.group().strip()
                        raise Exception(
                            'Unsafe "{0}" command in file {1}'.format(
                                unsafe, cql_file))

                text.write(content)
                text.write('\n')

        self.cql = text.getvalue()

    def generate_cql(self, keyspace_name, replication_factor=1, outfile=None):
        """Interpolate keyspace and replication into the CQL statements.

        If outfile is passed, the result will also be written
        there. The file will not be closed.
        """
        output = self.cql.replace('@@KEYSPACE@@', keyspace_name)
        output = output.replace('@@REPLICATION_FACTOR@@',
                                str(replication_factor))
        if outfile:
            outfile.write(output)
        return output
