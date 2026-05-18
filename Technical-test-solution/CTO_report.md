## 5. CTO Report

### Incident Summary

The ClickHouse staging cluster (master-master, 2 nodes, 3-node Keeper quorum) experienced a total replication failure affecting all 88+ tables across 4 databases. Inserts on `ch02` were not propagating to `ch01`. During investigation, `ch02` was also found to be in readonly mode, neither node was able to accept writes in a replicated context.

### Operational Impact

- **Total replication halt** : All 88+ tables across both nodes in readonly mode. No INSERT could be confirmed as replicated.
- **Inconsistent reads** : ch01 and ch02 held independent, diverged datasets. Any query across both nodes would return inconsistent results.
- **No failover possible** : ch01 could not serve as a standby for ch02.

### Confirmed Technical Cause

Two compounding failures, both introduced by the partial restore procedure described in My reasoning document:
1. **UUID mismatch across all tables.** The `ReplicatedMergeTree` engine uses the `{uuid}` macro in its ZooKeeper path. Tables on ch01 and ch02 were created in independent operations and received different UUIDs, placing them in completely separate Keeper namespaces. The two nodes had no awareness of each other across 88+ tables.

2. **Keeper volumes not restored.** The Keeper state machine held no registration for any replica on either node including ch02 itself. `SYSTEM RESTART REPLICA` cannot recover from this state because there is no existing path in Keeper to reconnect to.

### Corrective Actions Zero Downtime

Performed on running containers without restarting or stopping any service.

1. **UUID realignment on ch01.** A Python script queried ch02's UUID for each table, then dropped and recreated each table on ch01 with an explicit `UUID 'xxx'` clause matching ch02. This registered ch01 into the same Keeper namespace as ch02 for every table.

2. **Keeper registration via `SYSTEM RESTORE REPLICA` on ch02.** With ch01 now pointing at the correct paths, `SYSTEM RESTORE REPLICA` was executed on ch02 for all 88+ tables. This reconstructs Keeper metadata from the node's local disk. ch01 automatically appeared as the second replica once ch02's paths existed in Keeper.

Post-repair verification confirmed `is_readonly = 0`, `active_replicas = 2`, `total_replicas = 2` on all tables. A live INSERT on ch02 propagated to ch01.
