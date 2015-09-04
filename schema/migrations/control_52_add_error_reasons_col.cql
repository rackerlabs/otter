USE @@KEYSPACE@@;

-- Add "error_reasons" column to scaling_groups table

ALTER TABLE scaling_group
ADD error_reasons list<text>;
