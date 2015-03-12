USE @@KEYSPACE@@;

-- Delete "webhooks_by_token" index since "webhook_keys" table 
-- serves that purpose

DROP INDEX IF EXISTS webhooks_by_token;
