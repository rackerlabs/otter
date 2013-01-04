USE @@KEYSPACE@@;

-- KEY is <tenantID>:<coloID>:<groupID>
CREATE COLUMNFAMILY launch_config (KEY ascii PRIMARY KEY);