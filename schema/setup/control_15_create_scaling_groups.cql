USE @@KEYSPACE@@;

-- KEY is <tenantID>:<coloID>:<groupID>
CREATE COLUMNFAMILY accounting (KEY ascii PRIMARY KEY)
      WITH default_validation = counter;