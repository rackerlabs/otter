USE @@KEYSPACE@@;

-- Add "deleting" column to scaling_groups table

ALTER TABLE scaling_group
ADD error_reasons list<ascii>;
