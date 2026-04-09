# 14 - Repo Dependencies as DEPENDS_ON

One decision about the source of truth for `DEPENDS_ON` edges in the knowledge graph — switching from description keyword matching to structured dependency extraction.

---

## Decision 14: DEPENDS_ON Edge Source

**Context:** `DEPENDS_ON` edges in the knowledge graph express that one tracked repo uses another tracked repo as a dependency. For example, if repo A lists `reporium-api` in its `requirements.txt`, and `reporium-api` is itself a tracked repo in the database, then A `DEPENDS_ON` reporium-api. These edges are valuable for surfacing downstream impact during changes and for building dependency-aware rankings.

The `repo_dependencies` table exists separately: it is populated by a dependency extraction step that parses manifest files — `requirements.txt`, `package.json`, `go.mod`, `Cargo.toml` — and stores each declared package name alongside the repo that declared it.

**What we tried:** Computing `DEPENDS_ON` edges from keyword matching on repo descriptions. The enricher would scan a repo's description and README for mentions of other repo names or known project names. If the description contained the string `"uses reporium-api"` or `"built on top of X"`, a `DEPENDS_ON` edge was emitted.

**What broke:** The keyword-matching approach had poor precision. Repository descriptions are written for humans, not for structured extraction. A repo might mention another project in a comparison context ("similar to X, but for Y"), in a negative context ("does not require X"), or in a historical context ("originally built on X before switching"). All of these generated false positive edges.

Confidence scores assigned to these edges were arbitrarily set at 0.5 — acknowledging that the signal was weak — but even a 0.5-confidence `DEPENDS_ON` edge influences the graph structure. The edge set was noisy and inconsistent across runs because description content changed independently of actual dependency declarations.

Meanwhile, `repo_dependencies` was being populated but not connected to anything. The structured data — exact package names declared in manifest files — was sitting unused while the graph relied on unreliable text heuristics.

**Decision:** Switch the `DEPENDS_ON` edge source entirely to `repo_dependencies`.

The graph build queries `repo_dependencies` and attempts to match each `package_name` against the `name` field of repos in the `repositories` table. Matching is exact (normalized to lowercase). If a match is found, a `DEPENDS_ON` edge is emitted with confidence 0.95.

The confidence of 0.95 reflects the nature of the signal: a direct package-name match against a manifest file is high-signal. The 0.05 gap from 1.0 accounts for edge cases where a package name collision exists — two different packages with the same name in different ecosystems.

The `repo_dependencies` table is populated via two mechanisms: backfill migration 031 ran against all existing repos at the time of the schema change, and the real-time dependency extraction step in the ingestion pipeline populates it for each newly ingested or re-ingested repo.

**Tradeoff:** This approach only produces `DEPENDS_ON` edges when both the dependent repo and the dependency are tracked in the database. A Python repo that depends on an npm package will generate no `DEPENDS_ON` edge if that npm package is not itself a tracked repo. Cross-ecosystem dependencies are invisible to the graph.

This is a significant limitation. Many real-world dependencies — on PyPI packages, npm modules, or Go standard library packages — will never appear as tracked repos and will never generate edges. The graph's `DEPENDS_ON` coverage is limited to the subset of tracked repos that depend on other tracked repos.

This is still substantially better than the previous approach. The previous edges were frequently wrong. The current edges, when they appear, are almost always correct. A sparse-but-accurate graph is more useful than a dense-but-noisy one, particularly for downstream features like impact analysis and dependency ranking.

---
