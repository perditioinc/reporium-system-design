# 04 - Scale Analysis

## Current State (1,641+ repos)

| Metric | Value | Source |
|--------|-------|--------|
| Total repos tracked | 1,641+ | API /stats and index.json |
| Languages | 29 | API /stats |
| KG edges | 74,783 | Knowledge Graph |
| Embeddings | 1,680 | pgvector |
| forksync duration | 143s | SYNC_REPORT |
| forksync concurrency | 50 | asyncio.Semaphore(50) |
| Forks checked | 792 | SYNC_REPORT |
| Errors | 1 | SYNC_REPORT |
| reporium-db sync duration | 127.1s | LAST_RUN |
| API calls (db sync) | 9 | LAST_RUN |
| Rate limit remaining after sync | 4,764 | LAST_RUN |
| Rate limit budget | 5,000/hr | GitHub API |

The platform is healthy at current scale. Both sync jobs complete in under 3 minutes. Rate limit usage is minimal (~236 of 5,000 consumed, ~5%).

---

## Bottleneck Analysis by Tier

### Tier 1: 1,641 repos (current)

**Bottleneck:** None. Everything works.

- forksync: 143s, well within the nightly window
- reporium-db: 127.1s, 9 API calls
- Rate limit: ~5% consumed (~236/5,000)
- KG: 74,783 edges, 1,680 embeddings — no performance issues
- Neon: free tier, no issues
- File sizes: index.json ~2MB, manageable

### Tier 2: 2,000 repos

**Bottleneck:** None expected.

- forksync: ~170s estimated (linear scaling from 143s/792 forks)
- reporium-db: ~155s estimated (linear scaling from 127.1s/1,641 repos)
- Rate limit: ~3% consumed
- Total pipeline: under 6 minutes
- No architecture changes needed

### Tier 3: 10,000 repos

**Bottleneck:** Rate limits and file sizes.

- forksync: ~1,800s (30 minutes) at current concurrency
  - Fix: Increase semaphore to 100, use ETag caching aggressively
  - With ETags (most repos unchanged): ~600s estimated
- reporium-db: ~1,540s (25 minutes) at current rate
  - Fix: GraphQL pagination, batch writes
- Rate limit: ~1,500 calls, 30% consumed
  - Risk: Spikes could hit ceiling
  - Fix: Multi-token rotation
- index.json: ~24MB, still serviceable but slow to parse
  - Fix: Already partitioned, consumers use per-repo files
- Neon: Free tier limits may be reached
  - Fix: Move to Neon paid tier ($19/mo)

### Tier 4: 50,000 repos

**Bottleneck:** Rate limits, sync duration, database.

- forksync: 2.5+ hours even with 100 concurrency and ETags
  - Fix: Incremental sync (only check repos with recent upstream activity)
  - GraphQL `pushedAt` filter reduces check set by ~90%
- Rate limit: Multi-token required (3-4 tokens)
  - Each token: 5,000/hr, total budget: 15,000-20,000/hr
- reporium-db: Single-file commits break at this scale
  - Fix: Batch commits, consider moving to database-only
- Neon: Paid tier required, pgvector indexes need tuning
- Pipeline duration: Must split across multiple scheduling windows

### Tier 5: 100,000 repos

**Bottleneck:** Everything.

- forksync: Incremental sync mandatory, full sync impossible in one window
  - Shard by owner or language, run in parallel Cloud Run instances
- Rate limit: 5+ tokens with rotation, or GitHub App installation token (higher limits)
- reporium-db: GitHub raw files no longer viable as primary store
  - Move to database-only, use raw files as static export
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
| reporium-db sync | 18 | ~100 | ~1,000 |
| **Total** | **~236** | **~1,130** | **~11,300** |
| **Tokens needed** | 1 | 1 | 3 |

At current scale (1,641 repos), we use ~5% of a single token's budget. We have headroom to grow 6x before needing architectural changes.

---

## Schedule Tier Math

All times assume nightly execution starting at 02:00 UTC.

| Tier | forksync | db sync | ingestion | Total | Window OK? |
|------|----------|---------|-----------|-------|------------|
| 1,641 | 143s | 127s | N/A | ~5min | Yes |
| 2K | ~170s | ~155s | ~60s | ~7min | Yes |
| 10K | ~600s | ~400s | ~300s | ~22min | Yes |
| 50K | ~3,600s | ~1,800s | ~1,200s | ~110min | Tight |
| 100K | sharded | sharded | sharded | ~180min | Needs splitting |

The nightly window (02:00-06:00 UTC) gives us 4 hours. At 50K repos, we approach the limit and need to consider splitting the pipeline across multiple windows or running incremental syncs.
