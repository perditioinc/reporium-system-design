# Phase 2-3 Follow-ups

Status: draft

This note captures the post-backfill decisions that should drive the next
feature-completeness and scaling wave after Phase 1 observability lands.

## Decision 1: Frontend testing should start with Jest in the existing UI repo

Why:
- The current risk is regression in components and client-side data handling.
- The fastest path is to add Jest and coverage where the UI already lives,
  instead of splitting a component library before tests exist.

Guardrails:
- Start with smoke-level rendering and transform logic tests.
- Enforce coverage only on the new test paths first.
- Do not block deployment on broad legacy coverage immediately.

## Decision 2: `/library` freshness should be treated as a cache coherency issue

Why:
- `/stats` is already acting as the control signal for correct counts.
- The likely failure domain is cache invalidation or stale derived payloads,
  not source-of-truth corruption.

Guardrails:
- Compare `/library`, `/library/full`, and `/stats` on the same revision.
- Add an explicit freshness metric instead of relying on manual spot checks.
- Prefer targeted invalidation over TTL increases.

## Decision 3: Fork events should flow through a small enrichment orchestrator

Why:
- `forksync` is already publishing the right event boundary.
- `reporium-api` should not absorb heavy enrichment work inline.
- The orchestration layer needs idempotency and replay safety before it grows.

Guardrails:
- Accept events, write a durable ingest record, and fan out enrichment work.
- Keep subscribers idempotent by repo + event timestamp.
- Start with fork-related refresh only; avoid generic event expansion in v1.

## Decision 4: New graph edges should use additive schemas and versioned builders

Why:
- The current graph is stable after the DEPENDS_ON recovery.
- Future edge families like `SECURITY_DEPENDS_ON`, `LICENSE_COMPATIBLE`, and
  `DEPRECATED_BY` should not require index-breaking rewrites.

Guardrails:
- Add builders one edge type at a time.
- Store evidence and confidence with each edge family.
- Measure quality and coverage before exposing a new edge type in the UI.

## Suggested issue mapping

- `perditioinc/reporium`: Jest CI and coverage bootstrap
- `perditioinc/reporium-api`: `/library` freshness and cache coherency audit
- `perditioinc/reporium-events`: fork event enrichment orchestration design
- `perditioinc/reporium-system-design`: graph extensibility ADR and rollout plan
