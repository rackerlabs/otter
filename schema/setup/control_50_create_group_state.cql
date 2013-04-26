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

-- active is the active list.
-- format:
--   {"instanceid: {"name": "servername", "links": json_links_obj, "created": date}}
--
-- pending is the pending list.
-- format:
--  {"jobid": {"created": date}}
--
-- groupTouched is a timestamp of the last time a scaling policy
--  was executed in the group
--
-- policyTouched is a list of timestamps for the policy
--  {"policyid": date}

CREATE COLUMNFAMILY group_state (
    "tenantId" ascii,
    "groupId" ascii,
    active ascii,
    pending ascii,
    "groupTouched" ascii,
    "policyTouched" ascii,
    paused boolean,
    deleted boolean,
    PRIMARY KEY("tenantId", "groupId")
    );

CREATE INDEX deleted_group_state ON group_state (deleted);
