USE @@KEYSPACE@@;

-- Stores events to be scheduled in future
--
-- In CQL3, the primary key is split such that the first part
-- ends up in the row key, the rest of the key ends up
-- as a composite column key.
--
-- This does a good job of making things a bit more rational
-- than some of the CQL2 ecentricity.
--
-- My mother, who cut her teeth in those heady days of IMS
-- and mainframe computers, before Codd's relational model
-- will probably get the giggles looking at this.

CREATE TABLE scaling_schedule (
    "tenantId" ascii,
    "groupId" ascii,
    "policyId" ascii,
    trigger timestamp,
    cron ascii,
    PRIMARY KEY("policyId", "trigger")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;


-- New table to store scheduled events.

CREATE TABLE scaling_schedule_v2 (
    bucket int,
    "tenantId" ascii,
    "groupId" ascii,
    "policyId" ascii,
    trigger timestamp,
    cron ascii,
    version timeuuid,
    PRIMARY KEY(bucket, trigger, "policyId")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
