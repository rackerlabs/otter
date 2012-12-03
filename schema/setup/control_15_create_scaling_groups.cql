USE @@KEYSPACE@@;

-- KEY is <tenantID>:<coloID>:<groupID>
CREATE COLUMNFAMILY scaling_groups (KEY ascii PRIMARY KEY);