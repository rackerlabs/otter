USE @@KEYSPACE@@;

CREATE TABLE servers_cache (
    tenant_id ascii,
    group_id ascii,
    last_update timestamp,
    server_id ascii,
    server_blob ascii,
    PRIMARY KEY((tenant_id, group_id), last_fetch, server_id)
) WITH CLUSTERING ORDER BY (last_update DESC, server_id ASC) AND
compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
