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

CREATE TABLE policy_webhooks (
    "tenantId" ascii,
    "groupId" ascii,
    "policyId" ascii,
    "webhookId" ascii,
    data ascii,
    "webhookKey" ascii,
    deleted boolean,
    PRIMARY KEY("tenantId", "groupId", "policyId", "webhookId")
    );

CREATE INDEX deleted_policy_webhooks ON policy_webhooks (deleted);
CREATE INDEX webhooks_by_token ON policy_webhooks ("webhookKey");
