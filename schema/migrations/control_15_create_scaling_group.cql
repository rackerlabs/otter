USE @@KEYSPACE@@;

-- scaling_config table is renamed to scaling_group and other columns added to it
-- This file migrates by creating the table

CREATE COLUMNFAMILY scaling_group (
    "tenantId" ascii,
    "groupId" ascii,
    group_config ascii,
    launch_config ascii,
    active ascii,
    pending ascii,
    "groupTouched" ascii,
    "policyTouched" ascii,
    paused boolean,
    created_at timestamp,
    PRIMARY KEY("tenantId", "groupId")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
