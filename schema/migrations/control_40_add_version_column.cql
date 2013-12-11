USE @@KEYSPACE@@;

-- Add version column to scaling_policies table

ALTER TABLE scaling_policies
ADD version timeuuid;

