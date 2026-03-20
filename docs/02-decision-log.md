# 02 - Decision Log

Nine architecture decisions that shaped Reporium. Each entry explains what we tried, what broke, and why we changed.

---

## Decision 1: Sync Method

**Context:** Forks need to stay current with their upstream repositories. The initial approach used the GitHub merge-upstream API endpoint.

**What we tried:** `merge-upstream` via the REST API. It accepted the request, returned HTTP 200, and reported success. But the forks were not actually syncing. The response looked correct, the status code was correct, but the commits were not being pulled.

**What broke:** Silent failures. The API returned 200 even when the sync did not happen. We had no way to detect this without comparing commit SHAs before and after, which added complexity and API calls.

**Decision:** Switch to `gh repo sync`. This command either syncs the fork or returns a non-zero exit code. No ambiguity. If it fails, we know immediately.

**Tradeoff:** `gh repo sync` requires the GitHub CLI, which means our runtime needs it installed. Cloud Run images now include `gh`. The reliability gain is worth the image size increase.

---

## Decision 2: Sync Speed

**Context:** With 826 repos (792 forks to check), the sync job needs to finish within a reasonable window.

**What we tried:** Sequential REST API calls. Each call took roughly 1 second. 818 calls at 1 second each meant roughly 14 minutes for a full sync.

**What broke:** The job was too slow. 14 minutes is too long for a nightly maintenance window, especially when other jobs depend on it completing.

**Decision:** Switch to GraphQL batch queries for the fork list, then use `asyncio.Semaphore(50)` for concurrent sync operations. Total duration dropped to 143 seconds. We measured this from the SYNC_REPORT: 792 repos checked, 50 concurrent, 1 error, 143s total.

**Tradeoff:** Higher concurrency means more aggressive rate limit consumption. At 50 concurrent, we still stay well within the 5,000 requests/hour budget. The LAST_RUN file shows 9 API calls total and 4,876 rate limit remaining after a full run.

---

## Decision 3: Sync Infrastructure

**Context:** The sync job needs a runtime environment. GitHub Actions was the natural first choice.

**What we tried:** Running forksync as a GitHub Actions workflow.

**What broke:** GitHub Actions has a 6-minute timeout for jobs on the free tier. The sequential sync took 14 minutes. The job was killed every time before it could finish. Even after optimizing to 143s, Actions added cold-start overhead and had unpredictable queue times.

**Decision:** Move to Cloud Run with StreamingResponse. The job runs as an HTTP-triggered Cloud Run service. Cloud Scheduler sends the trigger at 02:00 UTC. StreamingResponse keeps the connection alive during the sync so Cloud Run does not kill the process.

**Tradeoff:** Cloud Run costs money (though minimal for a nightly job). We gain reliable execution, no timeout issues, and the ability to stream progress logs back to the caller.

---

## Decision 4: Data Storage Format

**Context:** reporium-db stores metadata for every tracked repo.

**What we tried:** A single `index.json` file containing all 826 repos.

**What broke:** Nothing yet. But a single JSON file does not scale. At 826 repos it is about 2MB. At 100K repos it would be 200MB+, which exceeds GitHub raw file size limits and makes partial reads impossible.

**Decision:** Partitioned JSON. One `index.json` with lightweight references, plus individual per-repo JSON files organized by owner. This lets consumers read only what they need and keeps individual file sizes small.

**Tradeoff:** More files means more commits during sync. But Git handles many small files well, and consumers can fetch individual repos without downloading the entire dataset.

---

## Decision 5: API Database

**Context:** reporium-api needs a database for search, stats, and metadata queries.

**What we tried (evaluated):** Cloud SQL PostgreSQL. Estimated cost: $7-10/month for the smallest instance.

**Decision:** Neon free tier. Neon provides serverless PostgreSQL with pgvector support at no cost. The database has 13 tables and handles all current query patterns. pgvector enables future semantic search without a database migration.

**Tradeoff:** Free tier has limits on compute hours and storage. If the platform grows significantly, we may need to move to a paid tier. But starting at $0 instead of $7-10/month is the right call for a platform that is still proving its value.

---

## Decision 6: Firestore Separation

**Context:** GCP Firestore was already in use in the perditio-platform project for other services.

**Decision:** Keep Firestore completely separate from Reporium. Firestore is used only for the events system and WhatsApp business integration. Reporium data lives in Neon and GitHub raw files.

**Rationale:** Mixing data stores for different bounded contexts creates coupling. If the events system changes its Firestore schema, Reporium should not be affected. Each system owns its data store.

---

## Decision 7: Redis for ETag Caching

**Context:** forksync makes API calls that return ETag headers. Caching ETags avoids redundant data transfer and reduces rate limit consumption.

**Decision:** Add GCP Memorystore (Redis) with a VPC connector. forksync stores ETags in Redis and sends `If-None-Match` headers on subsequent requests. When the upstream has not changed, GitHub returns 304 (not modified) which does not count against the rate limit.

**Tradeoff:** Memorystore requires a VPC connector, which adds network complexity. Redis is not yet integrated into the API serving path, only forksync uses it. Adding it to the API would require the API Cloud Run service to also connect to the VPC.

---

## Decision 8: API Deployment

**Context:** The API started as a local development server.

**Decision:** Deploy to Cloud Run. This unblocked three things simultaneously: live metrics collection, the public roadmap endpoint, and the portfolio showcase. The API is accessible at `https://reporium-api-573778300586.us-central1.run.app`.

**Tradeoff:** Cloud Run cold starts add latency on the first request after idle. For a portfolio/documentation API, this is acceptable. If the API served production traffic, we would need minimum instances configured.

---

## Decision 9: Event System

**Context:** Services currently communicate via direct API calls. forksync calls reporium-db directly. This creates tight coupling.

**Decision:** Design (not yet deploy) a GCP Pub/Sub event system. Services publish events (e.g., "sync completed") and other services subscribe to react. This decouples producers from consumers.

**Current state:** Designed but not deployed. The direct call pattern works for the current scale. Pub/Sub will be needed when we add more consumers or need retry/dead-letter capabilities.

**Tradeoff:** Pub/Sub adds operational complexity (topics, subscriptions, IAM permissions, dead-letter queues). At current scale, the direct call pattern is simpler and sufficient.
