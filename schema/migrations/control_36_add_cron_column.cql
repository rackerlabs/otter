USE @@KEYSPACE@@;

-- Add cron column to scaling_schedule table

ALTER TABLE scaling_schedule
ADD cron ascii;

