USE @@KEYSPACE@@;

CREATE TABLE audit_log (
    "tenantId" ascii,
    "logTime" timeuuid,
    "logEvent" ascii,
    PRIMARY KEY ("tenantId", "logTime")
) WITH COMPACT STORAGE;
