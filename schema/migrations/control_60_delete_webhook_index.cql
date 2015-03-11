USE @@KEYSPACE@@;

-- Delete "webhooks_by_token" index since "webhook_keys" table 
-- serves that purpose

DROP TABLE webhooks_by_token;
