USE @@KEYSPACE@@;

-- Add "status" column to scaling_groups table

ALTER TABLE scaling_group
ADD status ascii;
