# 07 - Diagrams

Five architecture diagrams for the Reporium platform. All diagrams use Mermaid syntax and render on GitHub.

---

## 1. Full Platform Architecture

```mermaid
graph TB
    subgraph GitHub["GitHub (826 repos, 29 languages)"]
        GH_API["GitHub REST + GraphQL API"]
        GH_RAW["GitHub Raw CDN (24h cache)"]
        GH_REPOS["826 Repositories (792 forks)"]
    end

    subgraph CloudRun["GCP Cloud Run (perditio-platform)"]
        FORKSYNC["forksync — Sync forks from upstream<br/>asyncio.Semaphore(50), 143s"]
        DB_SYNC["reporium-db sync — Build index.json<br/>127.1s, 9 API calls"]
        INGESTION["reporium-ingestion — AI enrichment<br/>(NOT RUNNING: 0 categories, 0 skills)"]
        API["reporium-api — /docs, /stats, /search<br/>Cloud Run always-on"]
    end

    subgraph Storage["Data Stores"]
        NEON["Neon PostgreSQL (CP)<br/>13 tables, pgvector enabled<br/>Free tier, $0/month"]
        REDIS["Redis Memorystore (CP/AP hybrid)<br/>ETag cache for forksync<br/>VPC connector"]
        FIRESTORE["GCP Firestore (AP)<br/>Events + WhatsApp only<br/>NOT used by Reporium"]
    end

    subgraph Scheduling["Scheduling"]
        SCHEDULER["GCP Cloud Scheduler<br/>02:00 UTC nightly trigger"]
        PUBSUB["GCP Pub/Sub<br/>(designed, not deployed)<br/>at-least-once delivery"]
    end

    subgraph Outputs["Outputs"]
        SYNC_REPORT["SYNC_REPORT — duration, repos checked, errors"]
        LAST_RUN["LAST_RUN — API calls, rate limit remaining"]
        INDEX_JSON["index.json — 826 repo references"]
        REPO_FILES["Per-repo JSON metadata files"]
    end

    SCHEDULER -->|"HTTP trigger at 02:00 UTC"| FORKSYNC
    FORKSYNC -->|"gh repo sync (792 forks, 50 concurrent)"| GH_REPOS
    FORKSYNC -->|"Write sync metrics"| SYNC_REPORT
    FORKSYNC -->|"Write API call stats"| LAST_RUN
    FORKSYNC -->|"Cache ETags via VPC"| REDIS
    FORKSYNC -->|"GraphQL batch queries"| GH_API

    DB_SYNC -->|"Query all repos"| GH_API
    DB_SYNC -->|"Write index and per-repo files"| INDEX_JSON
    DB_SYNC -->|"Write individual metadata"| REPO_FILES

    INGESTION -.->|"Read repo metadata (not running)"| INDEX_JSON
    INGESTION -.->|"Write categories and skills (not running)"| NEON

    API -->|"Read stats, search, metadata"| NEON
    API -.->|"Redis not yet on API path"| REDIS

    GH_RAW -->|"Serve index.json and repo files"| INDEX_JSON
    GH_RAW -->|"Serve per-repo metadata"| REPO_FILES
```

---

## 2. Nightly Pipeline Sequence

```mermaid
sequenceDiagram
    participant Scheduler as GCP Cloud Scheduler
    participant Forksync as forksync (Cloud Run)
    participant GitHub as GitHub API
    participant Redis as Redis Memorystore
    participant DBSync as reporium-db sync
    participant Neon as Neon PostgreSQL
    participant Ingestion as reporium-ingestion

    Note over Scheduler: 02:00 UTC nightly trigger
    Scheduler->>Forksync: HTTP POST /sync (StreamingResponse)

    Forksync->>GitHub: GraphQL query: list all forks
    GitHub-->>Forksync: 792 forks returned

    Forksync->>Redis: GET cached ETags for forks
    Redis-->>Forksync: Return cached ETags

    loop 792 forks, 50 concurrent (asyncio.Semaphore)
        Forksync->>GitHub: gh repo sync (with If-None-Match ETag)
        GitHub-->>Forksync: 200 (synced) or 304 (unchanged)
        Forksync->>Redis: SET updated ETag
    end

    Note over Forksync: Duration: 143s, 1 error
    Forksync->>GitHub: Commit SYNC_REPORT to repo
    Forksync->>GitHub: Commit LAST_RUN (9 calls, 4876 remaining)
    Forksync-->>Scheduler: 200 OK (sync complete)

    Note over DBSync: 02:05 UTC
    Scheduler->>DBSync: HTTP POST /build-index

    DBSync->>GitHub: Query all 826 repos (9 API calls)
    GitHub-->>DBSync: Repo metadata returned

    DBSync->>GitHub: Commit index.json (826 entries)
    DBSync->>GitHub: Commit per-repo JSON files

    Note over DBSync: Duration: 127.1s
    DBSync-->>Scheduler: 200 OK (index built)

    Note over Ingestion: NOT RUNNING
    Ingestion-->>Ingestion: 0 categories enriched, 0 AI skills
```

---

## 3. forksync v1 vs v2

```mermaid
graph TB
    subgraph V1["forksync v1 — Sequential REST"]
        V1_START["Start sync job"]
        V1_LIST["REST API: list forks (1 call per page)"]
        V1_LOOP["Sequential loop: 818 merge-upstream calls"]
        V1_CALL["merge-upstream API (returns 200 even on failure)"]
        V1_WAIT["Wait ~1s per call"]
        V1_TOTAL["Total: ~14 minutes (818 calls x 1s)"]
        V1_FAIL["GitHub Actions: 6-minute timeout KILLS job"]

        V1_START -->|"Step 1"| V1_LIST
        V1_LIST -->|"Step 2: for each fork"| V1_LOOP
        V1_LOOP -->|"Step 3"| V1_CALL
        V1_CALL -->|"Silent failure: 200 but no sync"| V1_WAIT
        V1_WAIT -->|"Next fork"| V1_LOOP
        V1_LOOP -->|"After all forks"| V1_TOTAL
        V1_TOTAL -->|"Exceeds timeout"| V1_FAIL
    end

    subgraph V2["forksync v2 — GraphQL + Concurrent"]
        V2_START["Start sync job"]
        V2_GRAPHQL["GraphQL batch query: list all forks (1 call)"]
        V2_SEMAPHORE["asyncio.Semaphore(50): 50 concurrent"]
        V2_SYNC["gh repo sync (fails loudly on error)"]
        V2_ETAG["Redis ETag cache: skip unchanged repos"]
        V2_TOTAL["Total: 143s (792 forks, 50 concurrent, 1 error)"]
        V2_REPORT["Write SYNC_REPORT and LAST_RUN"]
        V2_CLOUD["Cloud Run: no timeout, StreamingResponse"]

        V2_START -->|"Step 1"| V2_GRAPHQL
        V2_GRAPHQL -->|"Step 2: 50 at a time"| V2_SEMAPHORE
        V2_SEMAPHORE -->|"Step 3: each fork"| V2_SYNC
        V2_SYNC -->|"Cache ETag"| V2_ETAG
        V2_ETAG -->|"All forks complete"| V2_TOTAL
        V2_TOTAL -->|"Step 4"| V2_REPORT
        V2_REPORT -->|"Runs on"| V2_CLOUD
    end

    V1_FAIL -->|"Redesigned to"| V2_START
```

---

## 4. Data Store Selection Decision Tree

```mermaid
graph TB
    START["Need to store data"] -->|"What kind of data?"| KIND

    KIND -->|"Repo metadata for browsing"| BROWSING
    KIND -->|"Repo metadata for querying"| QUERYING
    KIND -->|"Cache / ephemeral"| CACHING
    KIND -->|"Events / messaging"| EVENTS
    KIND -->|"Cross-service communication"| MESSAGING

    BROWSING -->|"Acceptable staleness?"| STALE_CHECK
    STALE_CHECK -->|"24 hours OK"| GH_RAW["GitHub Raw Files (AP)<br/>Free, CDN-backed, 24h cache<br/>Used by: reporium-db"]
    STALE_CHECK -->|"Must be fresh"| NEON_QUERY["Neon PostgreSQL (CP)<br/>13 tables, pgvector<br/>Used by: reporium-api"]

    QUERYING -->|"Need full-text search?"| SEARCH_CHECK
    SEARCH_CHECK -->|"Yes"| NEON_SEARCH["Neon PostgreSQL (CP)<br/>pg_trgm + pgvector<br/>Used by: /search endpoint"]
    SEARCH_CHECK -->|"No, simple lookups"| GH_RAW

    CACHING -->|"What are we caching?"| CACHE_TYPE
    CACHE_TYPE -->|"ETags for API responses"| REDIS_ETAG["Redis Memorystore (CP/AP hybrid)<br/>VPC connector required<br/>Used by: forksync"]
    CACHE_TYPE -->|"Query results"| REDIS_QUERY["Redis Memorystore<br/>NOT YET on API path<br/>Planned for: reporium-api"]

    EVENTS -->|"Reporium data?"| REPORIUM_CHECK
    REPORIUM_CHECK -->|"No — events/WhatsApp"| FIRESTORE["GCP Firestore (AP)<br/>Events + WhatsApp business<br/>NOT used by Reporium"]
    REPORIUM_CHECK -->|"Yes"| NEON_EVENTS["Neon PostgreSQL (CP)<br/>Keeps Reporium data together"]

    MESSAGING -->|"Need decoupling?"| DECOUPLE
    DECOUPLE -->|"Yes"| PUBSUB["GCP Pub/Sub<br/>At-least-once delivery<br/>Designed, NOT deployed"]
    DECOUPLE -->|"No, direct OK"| DIRECT["Direct API calls<br/>Current approach<br/>Works at 826 repos"]
```

---

## 5. CAP Theorem Visualization

```mermaid
graph TB
    CAP["CAP Theorem<br/>Pick two of three guarantees"] -->|"Guarantee 1"| C["Consistency<br/>Every read returns the most recent write"]
    CAP -->|"Guarantee 2"| A["Availability<br/>Every request gets a response"]
    CAP -->|"Guarantee 3"| P["Partition Tolerance<br/>System works despite network failures"]

    subgraph CP_Systems["CP: Consistency + Partition Tolerance"]
        CP_DESC["Rejects requests during partition<br/>rather than serve stale data"]
        NEON_CP["Neon PostgreSQL<br/>API returns errors during partition<br/>Wrong counts are worse than brief downtime"]
    end

    subgraph AP_Systems["AP: Availability + Partition Tolerance"]
        AP_DESC["Serves stale data during partition<br/>rather than reject requests"]
        FIRESTORE_AP["GCP Firestore<br/>Events must not be dropped<br/>Stale context is acceptable"]
        GH_RAW_AP["GitHub Raw Files<br/>24h staleness built into design<br/>Nightly sync is inherently delayed"]
    end

    subgraph Hybrid["Hybrid: Graceful Degradation"]
        HYBRID_DESC["Falls back to uncached behavior<br/>when cache is unavailable"]
        REDIS_HYBRID["Redis Memorystore<br/>Cache miss = full API request<br/>No data lost either way"]
    end

    subgraph AtLeastOnce["At-Least-Once Delivery"]
        ALO_DESC["Messages may be delivered more than once<br/>Consumers must be idempotent"]
        PUBSUB_ALO["GCP Pub/Sub (designed, not deployed)<br/>Use upserts, check duplicate event IDs"]
    end

    C --- CP_Systems
    A --- AP_Systems
    P --- CP_Systems
    P --- AP_Systems
    P --- Hybrid
    P --- AtLeastOnce
```
