USE @@KEYSPACE@@;

-- Add "suspended" column to scaling_groups table

ALTER TABLE scaling_group
ADD suspended boolean;
