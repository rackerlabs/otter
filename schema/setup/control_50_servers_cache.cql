USE @@KEYSPACE@@;

CREATE TABLE servers_cache (
    "tenantId" ascii,
    "groupId" ascii,
    last_update timestamp,
    server_id ascii,
    server_blob ascii,
    server_as_active boolean,  -- Is this autoscale ACTIVE server?
    PRIMARY KEY(("tenantId", "groupId"), last_update, server_id)
) WITH CLUSTERING ORDER BY (last_update DESC, server_id ASC) AND
compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
