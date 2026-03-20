# 03 - CAP Theorem Analysis

## CAP in Plain English

The CAP theorem says a distributed system can provide at most two of three guarantees simultaneously:

- **Consistency (C):** Every read returns the most recent write. All nodes see the same data at the same time.
- **Availability (A):** Every request gets a response, even if some nodes are down.
- **Partition tolerance (P):** The system continues to operate even when network messages between nodes are lost or delayed.

In practice, network partitions happen. So the real choice is between consistency and availability when a partition occurs. A CP system rejects requests it cannot guarantee are correct. An AP system serves responses that might be stale.

---

## Reporium Data Store Analysis

### Neon PostgreSQL — CP

**What it stores:** 13 tables of repo metadata, stats, categories, search indexes.

**CAP choice:** Consistency + Partition tolerance. During a network partition, Neon will reject writes rather than accept potentially inconsistent data. This means the API may return errors briefly.

**Why CP is correct here:** The API serves stats like "826 repos tracked" and "29 languages." If these numbers were inconsistent (showing 826 on one request and 400 on the next), users would lose trust in the data. Brief API errors during a partition are better than wrong counts. The data is authoritative, so correctness matters more than uptime.

### GCP Firestore — AP

**What it stores:** Events and WhatsApp business data (not Reporium data, but part of the same GCP project).

**CAP choice:** Availability + Partition tolerance. Firestore in Datastore mode prioritizes availability. During a partition, it will serve potentially stale reads rather than rejecting requests.

**Why AP is correct here:** The events system needs to accept incoming events even during network issues. Dropping an event is worse than processing it with slightly stale context. Events are append-only, so eventual consistency is natural.

### Redis Memorystore — CP/AP Hybrid

**What it stores:** ETag cache entries for forksync.

**CAP choice:** Hybrid. Redis is a single-node cache in this deployment, so partitions mean "Redis is unreachable." When Redis is down, forksync falls back to making full API requests without ETag headers.

**Why hybrid is correct here:** The cache is an optimization, not a source of truth. When available, it provides consistent ETag values (CP behavior). When unreachable, the system degrades gracefully by skipping the cache (AP-like behavior at the application level). No data is lost either way.

### GitHub Raw Files — AP

**What it stores:** `index.json` and per-repo metadata files in reporium-db.

**CAP choice:** Availability + Partition tolerance. GitHub's CDN serves raw files with up to 24 hours of staleness. The files are always available, but may not reflect the most recent sync.

**Why AP is correct here:** These files serve the browsing and discovery use case. A user looking at repo metadata can tolerate data that is up to 24 hours old. The nightly sync pipeline updates the files once per day, so 24-hour staleness is inherent in the design regardless of CAP properties.

### GCP Pub/Sub — At-Least-Once Delivery

**What it handles:** Event messages between services (designed, not yet deployed).

**Delivery guarantee:** At-least-once. A message may be delivered more than once if the subscriber does not acknowledge it in time.

**Implication:** All consumers must be idempotent. Processing the same "sync completed" event twice should produce the same result as processing it once. This means consumers should use upserts instead of inserts and check for duplicate event IDs.

---

## Summary Table

| Store | CAP Choice | Failure Mode | Acceptable? |
|-------|-----------|--------------|-------------|
| Neon PostgreSQL | CP | Brief API errors during partition | Yes — wrong counts are worse |
| GCP Firestore | AP | Stale reads during partition | Yes — events must not be dropped |
| Redis Memorystore | CP/AP hybrid | Falls back to uncached requests | Yes — cache is optional |
| GitHub raw files | AP | Up to 24h stale data | Yes — nightly sync is inherently delayed |
| GCP Pub/Sub | At-least-once | Duplicate messages | Yes — consumers must be idempotent |
