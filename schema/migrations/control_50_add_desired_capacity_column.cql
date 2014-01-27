USE @@KEYSPACE@@;

-- Add a desired capacity column to the scaling_groups table

ALTER TABLE scaling_group
ADD desired varint;

