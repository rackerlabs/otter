"""
Code to load keyspaces and data into a running Cassandra cluster.

Uses the python CQL driver, becuase silverberg doesn't yet support connecting
without a defined keyspace.
"""

from cStringIO import StringIO
from glob import glob
import json
import os.path
import os
import re
import uuid

from cql.apivalues import ProgrammingError
from cql.connection import connect

from silverberg import client

from twisted.internet import endpoints, reactor


def simple_create_keyspace(keyspace_name, replication_dict=None):
    """
    Given a keyspace name, produce keyspace creation CQL (version 3 CQL).  No
    schema set up is done.  Uses a simple replication strategy and a
    replication factor of 1.

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


_table_regex = re.compile(
    '^\s*create\s+(?:table|columnfamily)\s+(?P<table>\S+)\s*\(',
    re.I | re.M)

_drop_regex = re.compile('^\s*(alter|drop|truncate|delete)\s', re.I | re.M)

cassandra_host = os.environ.get('CASSANDRA_HOST', 'localhost')
cassandra_port = os.environ.get('CASSANDRA_PORT', 9160)

class RunningCassandraCluster(object):
    """
    A resource representing an already running Cassandra cluster that cannot be
    stopped/started/initted.  This resource can never be "dirtied".

    This simply creates and destroys keyspaces in a blocking manner, since
    nothing can be done until the keyspace is created anyway.  Future possible
    enhancements:

    * support returning deferreds instead.

    :ivar host: the host to connect to (defaults to localhost)
    :type host: ``str``

    :ivar port: the port to connect to (defaults to 9160)
    :type port: ``int``

    :param cql_version: the version of cql to use (defaults to 3)
    :type cql_version: ``int``

    :param initialize_cql: an optional function that takes a keyspace name
        and returns a bunch of cql to execute to set up the keyspace (including
        creating it, setting up schemas, etc.).  If not provided, uses
        :func:`simple_create_keyspace` instead.
    :type initialize_cql: ``callable``

    TODO: a resource that starts cassandra processes if none are running, but:

    * how to tell if an already-running cassandra cluster is running
        on the ports that you want?  e.g. if you can't connect, how do you tell
        whether the existing cluster is broken or if one needs to be started
    * re-generating the cassandra.yaml file to run on different ports and also
        to write to a different data directory, so it doesn't clobber any
        already-running ones.

    Possible solutions: A standing-up-cassandra resource which has a dependency
    on a yaml and data dir generation resource, but how can we figure out from
    existing cassandra processes what ports they are listening on and what data
    dir they are using?
    """
    def __init__(self, host=cassandra_host, port=cassandra_port,
                 cql_version="3.0.4", setup_cql=None,
                 teardown_cql=None, overwrite_keyspaces=True):
        self.host = host
        self.port = port
        self.cql_version = cql_version
        self.setup_cql = setup_cql or simple_create_keyspace
        self.teardown_cql = teardown_cql or simple_drop_keyspace
        self.overwrite_keyspaces = overwrite_keyspaces

        self._connection = connect(self.host, self.port,
                                   cql_version=self.cql_version)

    def _get_cursor(self):
        try:
            cursor = self._connection.cursor()
        except ProgrammingError:
            self._connection = connect(self.host, self.port,
                                       cql_version=self.cql_version)
            # if this doesn't take, blow up
            cursor = self._connection.cursor()
        return cursor

    def _exec_cql(self, cql):
        """
        Execute some CQL, which can be a giant blob of commands with a `;`
        after each command.
        """
        cursor = self._get_cursor()
        statements = [x for x in cql.split(';') if x.strip()]
        params = [{}] * len(statements)
        result = cursor.executemany(statements, params)
        cursor.close()
        return result

    def _get_tables(self):
        """
        Take the creation CQL and identify which tables and column families
        were created.
        """
        return _table_regex.findall(self.setup_cql(''))

    def setup_keyspace(self, keyspace_name):
        """
        Creates a keyspace given the setup cql, which should include keyspace
        creation as well as schema setup.

        :param keyspace_name: what the name of the keyspace is to create
        :type keyspace_name: ``str``

        :raises: :class:`cql.apivalues.ProgrammingError` if there was an error
            executing the cql or connecting to the cluster
        """
        setup_cql = self.setup_cql(keyspace_name)
        try:
            self._exec_cql(setup_cql)
        except ProgrammingError as pe:
            if (self.overwrite_keyspaces and
                    "Cannot add existing keyspace" in pe.message):
                self.teardown_keyspace(keyspace_name)
                # only try one more time
                self._exec_cql(setup_cql)
            else:
                raise pe

    def teardown_keyspace(self, keyspace_name):
        """
        Drops a keyspace given the keyspace name.  If the keyspace doesn't
        exist Cassandra, do nothing.

        :param keyspace_name: what the name of the keyspace is to drop
        :type keyspace_name: ``str``
        """
        try:
            self._exec_cql(self.teardown_cql(keyspace_name))
        except ProgrammingError as pe:
            # if the keyspace doesn't exist, everything's fine
            if "Cannot drop non existing keyspace" not in pe.message:
                raise pe

    def truncate_keyspace(self, keyspace_name):
        """
        Truncates a keyspace (removes all data from all tables in the keyspace)

        :param keyspace_name: what the name of the keyspace is to drop
        :type keyspace_name: ``str``
        """
        tables = self._get_tables()
        if tables:
            cql = "USE {0}; {1};".format(
                keyspace_name,
                "; ".join(["TRUNCATE {0}".format(table) for table in tables]))
            self._exec_cql(cql)

    def dump_data(self, keyspace_name, dirpath):
        """
        Dumps all the data from every table in a keyspace to the specified
        directory path.  Data from each table will be in its own file.

        :param keyspace_name: what the name of the keyspace is to drop
        :type keyspace_name: ``str``

        :param dirpath: The directory to put the dumped data
        :type dirpath: ``str``
        """
        tables = self._get_tables()

        if tables:
            os.makedirs(dirpath)

        for table in tables:
            cursor = self._get_cursor()
            cursor.execute('USE {0}'.format(keyspace_name))
            cursor.execute('SELECT * FROM {0};'.format(table))
            with open(os.path.join(dirpath, table), 'wb') as dump:
                json.dump(cursor.description, dump)
                dump.write('\n\n')
                for row in cursor:
                    json.dump(row, dump)
                    dump.write('\n')
            cursor.close()

    def cleanup(self):
        """
        Cleanup connections
        """
        self._connection.close()


class CQLGenerator(object):
    """
    Reads all cql files from a particular directory in sorted order (by name),
    mashes them together.
    """
    def __init__(self, directory, safe_only=True):
        """
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
        """
        Replace keyspace and replication in the CQL.  Writes to a file if
        outfile is passed.
        """
        output = self.cql.replace('@@KEYSPACE@@', keyspace_name)
        output = output.replace('@@REPLICATION_FACTOR@@',
                                str(replication_factor))
        if outfile:
            outfile.write(output)
        return output


class KeyspaceWithClient(object):
    """
    Resource that represents a keyspace, and a Silverberg client for said
    keyspace, that can be dirtied.  When dirtied and then reset, the data
    can be optionally dumped, and then the data is truncated.

    This resource also cleans its connections (and keyspace) up when the
    reactor shuts down.

    :ivar client: the Silverberg client for this keyspace
    :type client: :class:``silverberg.client.CQLClient``
    """
    def __init__(self, cluster, keyspace_name):
        self._cluster = cluster
        self._keyspace_name = keyspace_name

        reactor.addSystemEventTrigger("before", "shutdown", self.cleanup)

        self._cluster.setup_keyspace(self._keyspace_name)
        self.client = client.CQLClient(
            endpoints.clientFromString(
                reactor,
                "tcp:{0}:{1}".format(self._cluster.host, self._cluster.port)),
            self._keyspace_name)

        self._dirtied = False

    def pause(self):
        """
        Pause this resource, for use at the end of tests.  It removes the
        client's connection from the reactor.  If not paused, there will be a
        dirty reactor warning.
        """
        # pause the silverberg client's transport
        if self.client._client._transport:
            self.client._client._transport.stopReading()
            self.client._client._transport.stopWriting()

    def resume(self):
        """
        Resumes this resource, for use at the start of tests.  It puts the
        client's connection back in the reactor, if not there.
        """
        # resume the silverberg client's transport
        if self.client._client._transport:
            self.client._client._transport.startReading()
            self.client._client._transport.startWriting()

    def dirtied(self):
        """
        Specify that this resource has been dirtied, so when reset is called
        the data gets truncated.
        """
        self._dirtied = True

    def reset(self, dumpdir=None):
        """
        If this resource is dirty, truncate the data (dump the data to
        ``dumpdir`` first, if specified).  Each table will be written to
        a different file (named for the table) in the dump directory.

        If the resource has not been dirtied, do nothing (not even dump data)

        :param dumpdir: the path to the directory to dump the data in
        :type dumpdir: ``str``
        """
        if not self._dirtied:
            return

        if dumpdir:
            self._cluster.dump_data(self._keyspace_name, dumpdir)
        self._cluster.truncate_keyspace(self._keyspace_name)

    def cleanup(self):
        """
        Clean up this resource by dropping the keyspace from the database
        and by closing the client's connection to the database.
        """
        self._cluster.teardown_keyspace(self._keyspace_name)
        try:
            return self.client._client.disconnect()
        except:
            pass


schema_dir = os.path.abspath(os.path.join(__file__, '../../../schema'))

class OtterKeymaster(object):
    """
    Object that keeps track of created keyspaces, PauseableSilverbergClients,
    and is a factory for PausableSilverbergClients
    """
    def __init__(self, host=cassandra_host, port=cassandra_port,
                 setup_generator=None):
        self.host = host
        self.port = port
        self.setup_generator = (
            setup_generator or CQLGenerator(schema_dir + '/setup'))

        self._keys = {}
        self.cluster = RunningCassandraCluster(
            host=host, port=port,
            setup_cql=(setup_generator or
                       CQLGenerator(schema_dir + '/setup').generate_cql))

    def get_keyspace(self, keyspace_name=None):
        """
        Get a keyspace resource named ``keyspace_name``.  If no name is
        specified, one will randomly be chosen.
        """
        # keyspaces must start with a letter, not a number
        keyspace_name = keyspace_name or ('a' + uuid.uuid4().hex)

        if not keyspace_name in self._keys:
            self._keys[keyspace_name] = KeyspaceWithClient(
                self.cluster, keyspace_name)
        return self._keys[keyspace_name]
