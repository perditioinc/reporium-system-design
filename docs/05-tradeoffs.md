# 05 - Tradeoffs

Eight active tradeoffs in the Reporium platform. Each one is a deliberate choice, not an oversight.

---

## 1. Ingestion Not Running

**What:** reporium-ingestion is designed but not deployed. Zero categories enriched, zero repos with AI skills.

**Why we accept this:** The sync pipeline (forksync + reporium-db) needed to be reliable first. Enrichment depends on clean, complete data. Running ingestion on top of broken sync would produce garbage categories. We verified on 2026-03-18 that categories enriched = 0 and repos_with_ai_skills = 0. This is expected.

**When to fix:** After forksync and reporium-db have run stably for 2+ weeks without manual intervention.

**Risk if ignored:** The API returns empty results for category and skill queries. Users see a working API with no enrichment data, which may look broken rather than "not yet implemented."

---

## 2. Neon Free Tier

**What:** The API database runs on Neon's free tier. Free tier has limits on compute hours (roughly 100 hours/month), storage (512MB), and connections.

**Why we accept this:** The platform is not serving production traffic. It is a portfolio project and internal tool. $0/month lets us prove the architecture without committing budget. Neon free tier includes pgvector, which is the main reason we chose it.

**When to fix:** When compute hours approach the limit (monitor via Neon dashboard) or when the API serves external users who expect SLAs.

**Risk if ignored:** The database goes to sleep during periods of inactivity. Cold starts add 2-5 seconds to the first query. This is noticeable in demos.

---

## 3. GitHub Raw Files Are 24 Hours Stale

**What:** reporium-db files served via GitHub's raw CDN may be cached for up to 24 hours. Consumers reading `https://raw.githubusercontent.com/...` may see yesterday's data.

**Why we accept this:** The nightly sync pipeline runs once per day. The data is inherently 24 hours old regardless of CDN caching. Staleness from the CDN is within the same window as staleness from the pipeline.

**When to fix:** If we move to real-time sync or if consumers need fresher data. Options: cache-busting query parameters, move to API-only serving.

**Risk if ignored:** Minimal. The 24-hour window is already baked into the design.

---

## 4. Redis Not on API Path

**What:** Redis Memorystore is connected to forksync via VPC connector but not to reporium-api. Every API request hits Neon directly.

**Why we accept this:** Adding the API to the VPC requires configuration changes and testing. At current traffic levels (low), Neon handles all queries without caching. Adding Redis to the API path is an optimization, not a requirement.

**When to fix:** When API latency becomes a problem (p99 > 500ms) or when Neon compute hours are being consumed too quickly by repeated identical queries.

**Risk if ignored:** Higher Neon compute usage, slower API responses under load. Not a problem at current scale.

---

## 5. Single GH_TOKEN

**What:** All GitHub API operations use a single personal access token. Rate limit: 5,000 requests per hour.

**Why we accept this:** Current usage is 124 requests per full sync cycle. That is 2.5% of the budget. We have 40x headroom.

**When to fix:** When repos exceed 10K (estimated 1,130 calls per cycle, 22% of budget) or when multiple jobs run concurrently and compete for the same token.

**Risk if ignored:** Rate limit exhaustion causes sync failures. forksync writes rate limit remaining to LAST_RUN, so we can monitor this.

---

## 6. SYNC_REPORT via GitHub API

**What:** forksync writes SYNC_REPORT and LAST_RUN as files committed to the repo via the GitHub API. This means sync metadata is stored in Git, not in a database.

**Why we accept this:** It is simple and auditable. Every sync run creates a commit with the report. We can see the full history of sync performance by reading Git log. No database needed for operational metrics.

**When to fix:** When the commit history becomes too large or when we need to query sync metrics programmatically (e.g., "show me all syncs slower than 200s"). At that point, write to Neon instead.

**Risk if ignored:** The repo accumulates commits from every sync run. At one commit per day, that is 365 commits per year. Manageable.

---

## 7. No Semver

**What:** None of the Reporium repos use semantic versioning or tags. There is no version tracking across the platform.

**Why we accept this:** The platform is in active development with a single maintainer. Semver adds overhead (tagging, changelogs, release notes) that slows down iteration when there are no consumers depending on stable versions.

**When to fix:** When other teams or external users depend on specific versions of the API or when we need rollback capabilities beyond "revert the last commit."

**Risk if ignored:** No clear way to communicate breaking changes. No rollback to a known-good version. Acceptable while the team is small.

---

## 8. API Not Integrated with Event System

**What:** The API does not publish or subscribe to Pub/Sub events. It reads directly from Neon and does not notify other services when data changes.

**Why we accept this:** The API is currently read-only. It does not modify data, so there are no state changes to broadcast. The event system (Pub/Sub) is designed for write-side operations like sync completion and enrichment triggers.

**When to fix:** When the API gains write endpoints (e.g., user bookmarks, manual categorization) or when other services need to react to API-side events.

**Risk if ignored:** If write endpoints are added without events, other services will not know about the changes. This is fine as long as the API stays read-only.
