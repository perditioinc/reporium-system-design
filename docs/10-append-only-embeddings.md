# 10 - Append-Only Embeddings

One decision about how we store vector embeddings for repos — switching from overwrite to history-preserving append-only rows.

---

## Decision 10: Embedding Storage Model

**Context:** `repo_embeddings` originally had `repo_id` as its primary key. One row per repo. Every ingestion run that produced a new embedding simply `UPDATE`d the existing row, overwriting the previous vector, the previous model name, and the previous timestamp.

**What we tried:** The single-row-per-repo model is conceptually clean. You always know where a repo's embedding lives. `SELECT * FROM repo_embeddings WHERE repo_id = $1` returns exactly one row and you are done.

**What broke:** We had no way to detect embedding drift. When the AI enricher switched model versions, or when a repo's README changed substantially, the old vector was silently replaced. If a downstream API regression appeared — cosine similarity scores shifting, semantic search returning different results — we could not determine whether the embedding itself had changed, what the previous vector looked like, or which ingestion run introduced the change. The table had no history at all. Rollback meant re-running the full enricher, which is expensive.

We also could not correlate embeddings with specific ingest runs. If a run failed partway through, we had no way to tell which repos had been enriched under the new model and which still carried vectors from a previous run.

**Decision:** Convert `repo_embeddings` to an append-only history table.

- Primary key changed from `repo_id` to a `UUID` generated at insert time.
- Added `is_current BOOLEAN NOT NULL DEFAULT FALSE`.
- Added `ingest_run_id UUID REFERENCES ingest_runs(id)` to link every embedding to the run that produced it.
- A partial unique index enforces at most one current row per repo: `UNIQUE(repo_id) WHERE is_current = TRUE`.
- On each ingestion, we `INSERT` the new row, then `UPDATE repo_embeddings SET is_current = FALSE WHERE repo_id = $1 AND is_current = TRUE` to retire the previous current row. Both operations run in a single transaction.

Historical rows are retained indefinitely. A future migration will add a retention policy if the table grows large.

**Tradeoff:** The HNSW index built for vector similarity search now includes all historical rows, not just current ones. Without filtering, similarity queries return stale vectors. Every query that touches `repo_embeddings` must include `WHERE is_current = TRUE`. This is straightforward to enforce in the API layer but requires discipline — a query missing the filter will silently return wrong results.

The table will grow proportionally to the number of ingestion runs multiplied by the number of repos. For the current scale (hundreds of repos, nightly runs), this is negligible. The ability to detect embedding drift, correlate vectors with specific model versions, and roll back to a previous embedding without re-enrichment is worth the storage cost and the mandatory filter clause.

---
