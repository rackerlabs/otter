"""
Code to load keyspaces and data into a running Cassandra cluster.

Uses the python CQL driver, becuase silverberg doesn't yet support connecting
without a defined keyspace.
"""

from cStringIO import StringIO
from glob import glob
import json
import os.path

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


class RunningCassandraCluster(object):
    """
    A resource representing an already running Cassandra cluster that cannot be
    stopped/started/initted.  This resource can never be "dirtied".

    This simply creates and destroys keyspaces in a blocking manner, since
    nothing can be done until the keyspace is created anyway.  Future possible
    enhancements:
        - support returning deferreds instead.

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
    - how to tell if an already-running cassandra cluster is running
        on the ports that you want?  e.g. if you can't connect, how do you tell
        whether the existing cluster is broken or if one needs to be started
    - re-generating the cassandra.yaml file to run on different ports and also
        to write to a different data directory, so it doesn't clobber any
        already-running ones.

    Possible solutions: A standing-up-cassandra resource which has a dependency
    on a yaml and data dir generation resource, but how can we figure out from
    existing cassandra processes what ports they are listening on and what data
    dir they are using?
    """
    def __init__(self, host="localhost", port=9160, cql_version="3",
                 setup_cql=None, teardown_cql=None, overwrite_keyspaces=True):
        self.host = host
        self.port = port
        self.cql_version = cql_version
        self.setup_cql = setup_cql or simple_create_keyspace
        self.teardown_cql = teardown_cql or simple_drop_keyspace
        self.overwrite_keyspaces = overwrite_keyspaces

        self._connection = connect(self.host, self.port,
                                   cql_version=self.cql_version)

    def _exec_cql(self, cql):
        """
        Execute some CQL, which can be a giant blob of commands with a `;`
        after each command.
        """
        try:
            cursor = self._connection.cursor()
        except ProgrammingError:
            self._connection = connect(self.host, self.port,
                                       cql_version=self.cql_version)
            # if this doesn't take, blow up
            cursor = self._connection.cursor()

        statements = [x for x in cql.split(';') if x.strip()]
        params = [{}] * len(statements)
        result = cursor.executemany(statements, params)
        cursor.close()
        return result

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

    def cleanup(self):
        """
        Cleanup connections
        """
        self._connection.close()


schema_dir = os.path.abspath(os.path.join(__file__, '../../../schema'))


class CQLGenerator(object):
    """
    Reads all cql files from a particular directory in sorted order (by name),
    mashes them together.
    """
    def __init__(self, directory):
        files = sorted(glob(os.path.join(directory, '*.cql')))
        text = StringIO()
        for cql_file in files:
            with open(cql_file) as fd:
                text.write(fd.read())

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


class PausableSilverbergClient(client.CQLClient):
    """
    A Silverberg client that can be paused and resumed and that makes sure it
    is disconnected before the reactor shuts down.
    """
    def __init__(self, *args, **kwargs):
        """
        Add a reactor hook to disconnect before shutting down
        """
        super(PausableSilverbergClient, self).__init__(*args, **kwargs)
        reactor.addSystemEventTrigger("before", "shutdown", self.cleanup)

    def pause(self):
        if self._client._transport:
            self._client._transport.stopReading()
            self._client._transport.stopWriting()

    def resume(self):
        if self._client._transport:
            self._client._transport.startReading()
            self._client._transport.startWriting()

    def cleanup(self):
        try:
            return self.disconnect()
        except:
            pass


class OtterKeymaster(object):
    """
    Object that keeps track of created keyspaces, PauseableSilverbergClients,
    and is a factory for PausableSilverbergClients
    """
    def __init__(self, host="localhost", port=9160, setup_generator=None):
        self.host = host
        self.port = port
        self.setup_generator = (
            setup_generator or CQLGenerator(schema_dir + '/setup'))

        self._keys = {}
        self.cluster = RunningCassandraCluster(
            host=host, port=port, setup_cql=self.setup_generator.generate_cql)

    def get_client(self, keyspace_name):
        if keyspace_name not in self._keys:
            self.cluster.setup_keyspace(keyspace_name)
            self._keys[keyspace_name] = PausableSilverbergClient(
                endpoints.clientFromString(reactor,
                    "tcp:{0}:{1}".format(self.host, self.port)),
                keyspace_name)
        return self._keys[keyspace_name]
