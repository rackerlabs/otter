Migrating away from manual soft deletes - this means that the tables must be altered to drop the 'deleted' column, and the indexes on said column dropped.

Except that CQL3 [does not support dropping columns yet](https://cassandra.apache.org/doc/cql3/CQL.html#alterTableStmt).

In the meantime, the indexes on that column can be dropped.
