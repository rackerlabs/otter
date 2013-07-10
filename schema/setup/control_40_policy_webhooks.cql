USE @@KEYSPACE@@;

-- Desired underlying structure is for the row key to be
-- the accounxt ID and the column key to be the group ID
-- plus the policy ID plus the webhook ID, with the data
-- contained as JSON
--
-- In CQL3, the primary key is split such that the first part
-- ends up in the row key, the rest of the key ends up
-- as a composite column key.
--
-- This does a good job of making things a bit more rational
-- than some of the CQL2 ecentricity.
--
-- There is also a reverse index on the unique token
--
-- My mother, who cut her teeth in those heady days of IMS
-- and mainframe computers, before Codd's relational model
-- will probably get the giggles looking at this.

-- data contains some useful information for the user and
-- including the name and metadata
-- format:
--   {"name": XXXXX, "metadata": {}}

-- capability has the version mapped to the hash (these will
-- be used for link generation)
-- format:
--   {"1": "hash"}

CREATE TABLE policy_webhooks (
    "tenantId" ascii,
    "groupId" ascii,
    "policyId" ascii,
    "webhookId" ascii,
    data ascii,
    capability ascii,
    "webhookKey" ascii,
    deleted boolean,
    PRIMARY KEY("tenantId", "groupId", "policyId", "webhookId")
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;

CREATE INDEX deleted_policy_webhooks ON policy_webhooks (deleted);
CREATE INDEX webhooks_by_token ON policy_webhooks ("webhookKey");
