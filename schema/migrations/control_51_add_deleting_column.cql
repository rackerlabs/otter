USE @@KEYSPACE@@;

-- Add "deleting" column to scaling_groups table

ALTER TABLE scaling_group
ADD deleting boolean;
