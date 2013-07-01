USE @@KEYSPACE@@;

-- Add the lock table, for managing locks similar to Netflix's Astyanax lock
-- recipe

CREATE TABLE locks (
    "lockId" ascii,
    "claimId" timeuuid,
    PRIMARY KEY ("lockId", "claimId")
    );
