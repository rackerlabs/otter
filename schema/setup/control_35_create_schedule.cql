USE @@KEYSPACE@@;

-- Desired underlying structure is for the row key to be
-- the account ID and the column key to be the group ID
-- plus the policy ID.
--
-- This is used as a trigger for the next
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
    PRIMARY KEY(trigger, "policyId")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
