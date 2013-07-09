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
