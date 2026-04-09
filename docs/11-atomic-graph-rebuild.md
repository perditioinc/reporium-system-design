# 11 - Atomic Graph Rebuild

One decision about how the knowledge graph is rebuilt — switching from delete-then-insert to a staging table swap with validation.

---

## Decision 11: Graph Rebuild Strategy

**Context:** The knowledge graph lives in the `repo_edges` table. It contains edges typed as `SIMILAR_TO`, `COMPATIBLE_WITH`, `DEPENDS_ON`, and `MAINTAINED_BY`. These edges are recomputed on every ingestion run — they are derived data, built from repo metadata, tag similarity, and dependency records. On each rebuild, the old edges become stale and must be replaced.

**What we tried:** A script that deleted all existing edges and then re-inserted the newly computed ones. The delete ran in one transaction; the insert loop ran in a separate series of transactions, one batch at a time.

**What broke:** A crash mid-rebuild — a network timeout, an OOM on the compute instance, a Neon connection drop — left `repo_edges` empty or partially populated. From the API's perspective, the knowledge graph had zero edges. The `/graph` endpoint returned empty results. The `/compatible` endpoint returned no compatible repos for anything. The problem was invisible unless you were actively checking edge counts, and recovery required re-running the full graph build from scratch.

There was no rollback. Once the delete committed, the old edges were gone. The insert loop had to complete successfully for the graph to be usable again. A partial run left a worse state than no run at all.

**Decision:** Switch to a staging table swap pattern.

The graph build now proceeds in four phases, all within a single outer transaction at the end:

1. **Build into staging.** All new edges are computed and inserted into a temporary staging table (`repo_edges_staging`). This takes as long as it takes. The production `repo_edges` table is untouched during this phase.

2. **Validate counts.** Before committing anything, compare edge counts in staging against the previous run's counts (stored in `ingest_runs.prev_edge_counts`). If any edge type drops by more than 50% relative to the prior run, the build aborts. A 50% drop almost always means something went wrong upstream — a data source returned empty, a filter was applied incorrectly, or a dependency lookup failed.

3. **Swap in a single transaction.** Archive the current edges to `repo_edges_archive` (for forensic use), delete from `repo_edges`, insert from `repo_edges_staging`, and commit. This is a single atomic transaction. Either the entire swap succeeds or nothing changes.

4. **Clean up staging.** Drop the temporary table after the commit.

If the process crashes before the swap transaction starts, `repo_edges` is unchanged. The API continues serving the previous graph. If validation fails, the run aborts with a logged error and the prior graph remains in place.

**Tradeoff:** The staging table holds a full copy of all edges while the build is running. For a graph with hundreds of thousands of edges, this requires transient disk space roughly equal to the size of `repo_edges` itself. On Neon's free tier this is within limits, but it is a real cost. The staging table is dropped immediately after the swap, so the overhead is temporary.

The 50% drop threshold is a heuristic. A legitimate graph restructuring — removing an entire edge type, for example — would trigger a false abort. In that case the threshold can be adjusted or bypassed with an explicit flag. The default is deliberately conservative.

---
