USE @@KEYSPACE@@;

-- KEY is <tenantID>:<coloID>:<groupID>
CREATE TABLE scaling_policies (groupId ascii, polId ascii, PRIMARY KEY(groupId, polId) );