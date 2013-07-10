USE @@KEYSPACE@@;

-- A large number of tombstones causes very slow range queries and full
-- row reads.

-- See https://issues.rax.io/browse/AUTO-433 and
--     https://issues.apache.org/jira/browse/CASSANDRA-5677.

ALTER TABLE scaling_config WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE launch_config WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE scaling_policies WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE scaling_schedule WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE policy_webhooks WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE group_state WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

ALTER TABLE locks WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
