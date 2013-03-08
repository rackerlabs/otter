USE @@KEYSPACE@@;

-- Desired underlying structure is for the row key to be
-- the account ID, the column key to be the group ID, with
-- the data contained as JSON
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

CREATE COLUMNFAMILY group_state (
    "tenantId" ascii,
    "groupId" ascii, 
    active ascii, 
    pending ascii,
    group_touched ascii,
    policy_touched ascii,
    deleted boolean,
    PRIMARY KEY("tenantId", "groupId")
    );
    
CREATE INDEX deleted_launch_config ON group_state (deleted);