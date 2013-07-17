-- Migrating away from manual soft deletes - this means that the tables must be
-- altered to drop the 'deleted' column, and the indexes on said column dropped.

-- Except that CQL3 does not support dropping columns yet:
-- https://cassandra.apache.org/doc/cql3/CQL.html#alterTableStmt

-- In the meantime, the indexes on that column can be dropped.


USE @@KEYSPACE@@;

-- from control_15_create_scaling_groups.cql
DROP INDEX deleted_scaling_config;

-- from control_20_create_launch_configs.cql
DROP INDEX deleted_launch_config;

-- from control_30_create_scaling_policies.cql
DROP INDEX deleted_scaling_policies;

-- from control_40_policy_webhooks.cql
DROP INDEX deleted_policy_webhooks;

-- from control_50_create_group_state.cql
DROP INDEX deleted_group_state;
