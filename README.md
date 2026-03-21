# reporium-system-design

Architecture documentation, decision logs, and system diagrams for the Reporium platform.

<!-- perditio-badges suite=Reporium workflow=test.yml -->
[![CI](https://github.com/perditioinc/reporium-system-design/actions/workflows/test.yml/badge.svg)](https://github.com/perditioinc/reporium-system-design/actions/workflows/test.yml)

---

## Platform at a Glance

```
  GitHub (826 repos)
        |
        v
  +--------------+       +----------------+
  | forksync     |------>| reporium-db    |
  | (Cloud Run)  |       | (JSON + index) |
  +--------------+       +----------------+
        |                        |
        v                        v
  +--------------+       +----------------+
  | reporium-    |       | reporium-api   |
  | ingestion    |       | (Cloud Run)    |
  +--------------+       +----------------+
        |                        |
        v                        v
  +--------------+       +----------------+
  | Neon (pg)    |<------| Redis          |
  | 13 tables    |       | (Memorystore)  |
  +--------------+       +----------------+
        |
        v
  +--------------+
  | /docs, /stats|
  | /search      |
  +--------------+
```

## Live Stats

| Metric | Value |
|--------|-------|
| Repos tracked | 826 |
| Languages | 29 |
| Public repos | 50+ |
| Neon tables | 13 |
| forksync duration | 143s |
| forksync concurrency | 50 |
| API calls per sync | 9 |
| Categories enriched | 0 (ingestion not running) |
| Repos with AI skills | 0 |

## Documentation

| Doc | Description |
|-----|-------------|
| [01 - Platform Overview](docs/01-platform-overview.md) | Component inventory, data flows, pipeline schedule |
| [02 - Decision Log](docs/02-decision-log.md) | 9 architecture decisions with full context |
| [03 - CAP Theorem](docs/03-cap-theorem.md) | CAP analysis for every data store |
| [04 - Scale Analysis](docs/04-scale-analysis.md) | Bottleneck analysis from 826 to 100K repos |
| [05 - Tradeoffs](docs/05-tradeoffs.md) | 8 active tradeoffs and their rationale |
| [06 - Working with Engineers](docs/06-working-with-engineers.md) | Real examples of collaboration and communication |
| [07 - Diagrams](docs/07-diagrams.md) | 5 Mermaid architecture diagrams |
| [08 - Demo Guide](docs/08-demo-guide.md) | How to present the platform to different audiences |
| [09 - Navigating Ambiguity](docs/09-navigating-ambiguity.md) | Framework for decisions under uncertainty |

## API

Base URL: Set `REPORIUM_API_URL` in your environment (see `.env.example`)

| Endpoint | Description |
|----------|-------------|
| `GET /docs` | Interactive API documentation |
| `GET /stats` | Platform statistics |
| `GET /search?q=` | Full-text repo search |

## GCP Project

`perditio-platform`
