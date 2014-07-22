USE @@KEYSPACE@@;

-- Stores servers in scaling group

CREATE TABLE servers (
    "tenantId" ascii,      -- Tenant ID of the user
    "groupId" ascii,       -- ID of one of the groups of tenant
    id ascii,              -- ID of server, NOT nova ID
    nova_id ascii,         -- Nova server ID
    status ascii,          -- Server status: one of "pending" or "active"
    created timestamp,     -- When the was server created
    lb_info ascii,         -- Load balancer info as JSON string
    PRIMARY KEY (("tenantId", "groupId"), id)
) WITH compaction = {
    'class' : 'SizeTieredCompactionStrategy',
    'min_threshold' : '2'
} AND gc_grace_seconds = 3600;
