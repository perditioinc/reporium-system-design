# 12 - Ingest Runs Provenance

One decision about what the `ingest_runs` table tracks — expanding it from a status log into a full provenance record for each ingestion.

---

## Decision 12: Run Provenance Schema

**Context:** The `ingest_runs` table originally recorded four things: the run mode (`full` or `incremental`), the run status (`pending`, `running`, `completed`, `failed`), the start timestamp, and the end timestamp. This was enough to answer "did the last run succeed?" and "how long did it take?" Nothing more.

**What we tried:** Operating with the minimal schema. When a run completed normally, the status field was sufficient. We could see that a run had finished and when.

**What broke:** Three separate problems emerged as ingestion grew more complex.

First, crashes mid-run were opaque. A run would transition to `running` and then never update again. The process had died, but the row showed `running` indefinitely. There was no record of which phase the run had reached before it crashed, how many edges had been built so far, or where a resume attempt should pick up.

Second, we could not associate edges with the run that built them. `repo_edges` had no foreign key back to `ingest_runs`. If we suspected that a specific run had introduced bad edges — wrong edge weights, edges built from a corrupted tag set, `DEPENDS_ON` edges computed against stale dependency data — we had no way to isolate and remove just those edges. The only option was a full graph rebuild.

Third, the 50% drop validation in the graph rebuild (see ADR 11) needed a baseline to compare against. There was nowhere to store the prior run's edge counts. We were computing the current counts but had nothing to validate them against.

**Decision:** Expand `ingest_runs` with four additional columns.

- `checkpoint_data JSONB`: Written periodically during the run. Contains the current phase name and a snapshot of edge counts by type computed so far. On crash recovery, the resumption logic reads `checkpoint_data` to determine where to restart. Example structure: `{"phase": "graph_build", "edge_counts": {"SIMILAR_TO": 1240, "COMPATIBLE_WITH": 870}}`.

- `prev_edge_counts JSONB`: Copied from the prior run's final edge counts at the start of each new run. This is the baseline the validation step compares staging counts against. Storing it on the run row means validation is self-contained — it does not need to query a separate run or reconstruct history.

- `git_sha TEXT`: The git commit SHA of the ingestion codebase at the time of the run. Populated from the `GIT_SHA` environment variable injected at container build time. This lets us correlate behavioral changes in the graph with code changes.

- `triggered_by TEXT`: How the run was initiated — `scheduler` for Cloud Scheduler nightly triggers, `manual` for operator-initiated runs, `backfill` for migration-driven runs. Useful for filtering logs and understanding whether anomalous behavior came from automated or manual execution.

Additionally, `repo_edges` gained `ingest_run_id UUID REFERENCES ingest_runs(id)`. Every edge written during a build carries the run that produced it. Forensic queries like "show me all edges built by run X" or "delete edges built before run Y" are now possible.

**Tradeoff:** Individual `ingest_runs` rows are larger. `checkpoint_data` and `prev_edge_counts` can each reach a few kilobytes for large graphs. At one run per day this is trivial. The `ingest_runs` table will accumulate rows over time, but it is append-only and small relative to `repo_edges` — a retention policy can be added later if needed.

The `ingest_run_id` FK on `repo_edges` means every edge insert must carry the run ID. This requires the run ID to be passed through the entire build pipeline, which adds a parameter to several internal functions. The alternative — looking up the current run ID from a global or a database query — introduces coupling. Explicit passing is the right call.

---
