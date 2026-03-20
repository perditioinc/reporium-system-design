# 01 - Platform Overview

Reporium is a platform that syncs, indexes, enriches, and serves metadata for 826 GitHub repositories across 29 languages.

## Component Inventory

| Repo | Purpose | Deployment | Data Owned | Cron Schedule |
|------|---------|------------|------------|---------------|
| `forksync` | Syncs forks from upstream | Cloud Run (streaming) | SYNC_REPORT, LAST_RUN | Nightly 02:00 UTC |
| `reporium-db` | Stores repo metadata as partitioned JSON | GitHub raw files | `index.json`, per-repo JSON | Nightly after forksync |
| `reporium-ingestion` | Enriches repos with AI categories/skills | Cloud Run (planned) | Neon: categories, skills | Not running |
| `reporium-api` | Serves stats, search, docs | Cloud Run | Neon: 13 tables | Always on |
| `reporium-system-design` | Architecture docs and diagrams | GitHub Pages (static) | This repo | N/A |

## Data Flows

### Nightly Sync Pipeline

1. **forksync** wakes at 02:00 UTC via Cloud Scheduler.
2. It reads the fork list from the GitHub API using GraphQL batch queries.
3. For each fork, it runs `gh repo sync` to pull upstream changes. 50 forks run concurrently via `asyncio.Semaphore(50)`.
4. After all syncs complete, forksync writes a SYNC_REPORT to the repo (duration, repos checked, errors) and a LAST_RUN file with API call count and rate limit remaining.
5. **reporium-db** sync runs next. It queries the GitHub API for all repos, builds `index.json` and per-repo metadata files. Duration: 127.1s, 9 API calls, 4,876 rate limit remaining after completion.
6. **reporium-ingestion** (not yet running) would read from reporium-db and enrich repos with AI-generated categories and skills, writing results to Neon.

### API Serving

1. **reporium-api** serves read traffic from Neon PostgreSQL (pgvector enabled).
2. Redis Memorystore caches ETag responses for forksync. Connected via VPC connector.
3. The API exposes `/docs`, `/stats`, and `/search` endpoints.

## Nightly Pipeline Schedule

| Time (UTC) | Job | Duration | Depends On |
|------------|-----|----------|------------|
| 02:00 | forksync | ~143s | GitHub API |
| 02:05 | reporium-db sync | ~127s | forksync completion |
| 02:10 | reporium-ingestion | N/A (not running) | reporium-db sync |

## What Is Not Yet Working

| Component | Status | Impact |
|-----------|--------|--------|
| reporium-ingestion | Not running | 0 categories enriched, 0 repos with AI skills |
| Redis on API path | Not integrated | API reads hit Neon directly every time |
| Event system (Pub/Sub) | Designed, not deployed | Services coupled via direct calls |
| Semver releases | No tagging | No version tracking across repos |
| Multi-token rotation | Single GH_TOKEN | 5,000 req/hr ceiling |
