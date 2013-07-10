USE @@KEYSPACE@@;

-- Add the lock table, for managing locks similar to Netflix's Astyanax lock
-- recipe

CREATE TABLE locks (
    "lockId" ascii,
    "claimId" timeuuid,
    PRIMARY KEY ("lockId", "claimId")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
