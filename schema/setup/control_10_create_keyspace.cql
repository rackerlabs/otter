--- We've got things paramaterized using the makefile.
---
--- The replication factor will definately change between dev and
--- production

CREATE KEYSPACE @@KEYSPACE@@ WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '@@REPLICATION_FACTOR@@'};