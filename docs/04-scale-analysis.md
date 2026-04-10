# 04 - Scale Analysis

## Current State (1,641 repos)

| Metric | Value | Source |
|--------|-------|--------|
| Total repos tracked | 1,641 | API /stats |
| Languages | 35+ | API /stats |
| forksync duration | ~300s (est.) | Linear from 826-repo baseline |
| forksync concurrency | 50 | asyncio.Semaphore(50) |
| reporium-db sync duration | ~250s (est.) | Linear from 826-repo baseline |
| Rate limit remaining after sync | ~4,765 | Estimated (235/5,000 consumed) |
| Rate limit budget | 5,000/hr | GitHub API |
| Knowledge Graph edges | 74,783 | repo_edges (ALTERNATIVE_TO + COMPATIBLE_WITH) |
| Active embeddings | 1,680 | repo_embeddings (append-only history) |
| Graph rebuild strategy | Atomic swap via ingest_runs | Migration 034 |

The platform is healthy at current scale. Both sync jobs complete in under 6 minutes. Rate limit usage remains minimal (~5% of budget). The knowledge graph and embedding layers are fully operational with atomic rebuild guarantees.

---

## Architecture Changes Since 826-Repo Baseline

Since the initial scale analysis, three major data-layer additions have been shipped:

### Knowledge Graph (Wave 2–3)
- `repo_edges` table: 74,783 edges of type `ALTERNATIVE_TO` and `COMPATIBLE_WITH`
- Atomic rebuild pattern: graph is built in a staging table (`repo_edges_new`) and swapped atomically into `repo_edges` on success via `ingest_runs` provenance tracking
- Edge archival: replaced edges are moved to `repo_edges_archive` rather than deleted, preserving history
- Build trigger: `build_knowledge_graph.py` runs post-ingestion; tracked in `ingest_runs` with `mode=graph_build`

### Append-Only Embeddings (Wave 3)
- `repo_embeddings` table: 1,680 active rows (one per repo, current model snapshot)
- Schema: `(repo_name, model, embedding, created_at)` — new embeddings are inserted, old rows are never deleted
- Enables full model-migration history without destructive updates
- Embedding generation is gated on `ingest_runs` success before commit

### Ingest Runs Provenance (Wave 3)
- `ingest_runs` table tracks every pipeline execution: `run_id`, `mode`, `status`, `repos_upserted`, `started_at`, `finished_at`
- Graph builds and embedding jobs reference `ingest_runs` for atomicity guarantees
- Enables replay and audit of all ingestion operations

---

## Bottleneck Analysis by Tier

### Tier 1: 1,641 repos (current)

**Bottleneck:** None. Everything works.

- forksync: ~300s, well within the nightly window
- reporium-db: ~250s, under 5 API calls per sync
- Rate limit: ~5% consumed (~235/5,000)
- Neon: free tier, no storage issues (legacy tables archived Apr 9)
- Knowledge graph: build completes in ~2 minutes post-ingestion
- Embeddings: 1,680 rows, pgvector cosine similarity fast at this size

### Tier 2: 5,000 repos

**Bottleneck:** None expected; KG build time grows.

- forksync: ~900s (15 minutes) estimated
- reporium-db: ~760s estimated
- Rate limit: ~14% consumed (~715/5,000)
- KG edges: ~230,000 estimated (linear from 74,783/1,641 density)
- KG build: ~5-7 minutes; still atomic-swap viable
- Embeddings: ~5,000 rows; pgvector still fast with HNSW index
- No architecture changes needed

### Tier 3: 10,000 repos

**Bottleneck:** Rate limits and KG build time.

- forksync: ~1,800s (30 minutes) at current concurrency
  - Fix: Increase semaphore to 100, use ETag caching aggressively
  - With ETags (most repos unchanged): ~600s estimated
- reporium-db: ~1,540s (25 minutes) at current rate
  - Fix: GraphQL pagination, batch writes
- Rate limit: ~1,500 calls, 30% consumed
  - Risk: Spikes could hit ceiling
  - Fix: Multi-token rotation
- KG edges: ~455,000 estimated; build time ~10-15 minutes
  - Risk: Staging table swap may stress Neon free tier
  - Fix: Neon paid tier, add index on `repo_edges_new` before swap
- Embeddings: ~10,000 rows; HNSW index rebuild on large inserts becomes noticeable
- index.json: ~24MB, still serviceable but slow to parse
  - Fix: Already paginated at API layer (pageSize=500)

### Tier 4: 50,000 repos

**Bottleneck:** Rate limits, sync duration, database, KG build.

- forksync: 2.5+ hours even with 100 concurrency and ETags
  - Fix: Incremental sync (only check repos with recent upstream activity)
  - GraphQL `pushedAt` filter reduces check set by ~90%
- Rate limit: Multi-token required (3-4 tokens)
  - Each token: 5,000/hr, total budget: 15,000-20,000/hr
- reporium-db: Single-file commits break at this scale
  - Fix: Batch commits, consider moving to database-only
- KG edges: ~2.3M estimated; atomic swap no longer viable in a single transaction
  - Fix: Partition graph by category or shard by edge type; incremental edge updates
- Embeddings: ~50,000 rows; pgvector HNSW index tuning required (`m`, `ef_construction`)
- Neon: Paid tier required, pgvector indexes need tuning
- Pipeline duration: Must split across multiple scheduling windows

### Tier 5: 100,000 repos

**Bottleneck:** Everything.

- forksync: Incremental sync mandatory, full sync impossible in one window
  - Shard by owner or language, run in parallel Cloud Run instances
- Rate limit: 5+ tokens with rotation, or GitHub App installation token (higher limits)
- reporium-db: GitHub raw files no longer viable as primary store
  - Move to database-only, use raw files as static export
- KG edges: ~4.6M estimated; dedicated graph database (e.g. Neo4j) may be warranted
- Embeddings: ~100,000 rows; dedicated vector store (Pinecone, Weaviate) likely needed
- Neon: Dedicated instance, connection pooling, read replicas
- Pub/Sub: Required for decoupling at this scale
- Estimated infra cost: $50-100/month

---

## Rate Limit Budget Calculation

GitHub API rate limit: 5,000 requests per hour per token.

| Operation | Calls at 1,641 | Calls at 10K | Calls at 100K |
|-----------|----------------|-------------|--------------|
| forksync (GraphQL) | ~18 | ~30 | ~300 |
| forksync (sync calls) | ~200 (ETags) | ~1,000 | ~10,000 |
| reporium-db sync | ~18 | ~100 | ~1,000 |
| **Total** | **~235** | **~1,130** | **~11,300** |
| **Tokens needed** | 1 | 1 | 3 |

At current scale (1,641 repos), we use ~5% of a single token's budget. We have headroom to grow 6x before needing architectural changes to the sync layer.

---

## Schedule Tier Math

All times assume nightly execution starting at 02:00 UTC.

| Tier | forksync | db sync | ingestion | KG build | Total | Window OK? |
|------|----------|---------|-----------|----------|-------|------------|
| 1,641 | ~300s | ~250s | ~120s | ~120s | ~13min | Yes |
| 5K | ~900s | ~760s | ~300s | ~420s | ~40min | Yes |
| 10K | ~600s* | ~400s | ~300s | ~900s | ~37min* | Yes |
| 50K | ~3,600s | ~1,800s | ~1,200s | ~3,600s | ~180min | Tight |
| 100K | sharded | sharded | sharded | sharded | ~360min | Needs splitting |

\* With ETag optimization at 10K tier.

The nightly window (02:00-06:00 UTC) gives us 4 hours. At 50K repos, we approach the limit and need to consider splitting the pipeline across multiple windows or running incremental syncs. The KG build is the new bottleneck at scale - it grows roughly linearly with edge count, which grows faster than repo count.