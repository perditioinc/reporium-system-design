# Company Knowledge Base — Reporium Reuse Plan

**Date:** 2026-05-17 · **Author:** Claude (code-grounded audit) · **Status:** PLAN ONLY — no code written
**Scope:** Can Reporium's RAG architecture be repurposed from a GitHub-repo corpus to PERDITIO's operational knowledge (Notion/Drive docs, WhatsApp threads, payment exports, creator contracts, event post-mortems, people files)?
**Verdict up front:** Yes. The plumbing is corpus-agnostic. The corpus coupling lives in exactly **four narrow places**: the regex router patterns, the `Repo` model + migrations, the GitHub source adapter, and the enrichment prompt. Everything else is reusable.

---

## 1. Actual architecture, from the code

Four repos, not three. `reporium-api` is a FastAPI service on Cloud Run backed by Postgres + pgvector (`reporium-api/app/main.py`, asgi app `app.main:app`; models in `app/models/repo.py`; Alembic in `migrations/versions/` 001–040). `reporium-ingestion` is a Python 3.12 async **Cloud Run Job** (`reporium-ingestion/ingestion/__main__.py` → `ingestion/main.py:run_ingestion()`, line 466) that reads GitHub, AI-enriches with Claude, embeds locally, and batch-POSTs to the API. `reporium` is a Next.js 16 App Router site on Vercel (`reporium/src/lib/dataProvider.ts`, `src/components/AskPanel.tsx`). A fourth repo, **`reporium-evals`**, is a standalone live-API eval runner (`reporium-evals/golden/ask_questions.yaml`, `runner/test_ask_eval.py`). Data flow: ingestion fetches a source item → parses/chunks → Claude enrichment (`ingestion/enrichers/ai_enricher.py`) → MiniLM-L6-v2 384-dim embedding (`ingestion/enrichment/embeddings.py`) → `POST /ingest/repos` (`ingestion/api/client.py`, batches of 50) → Postgres. Query path: frontend → `POST /intelligence/ask` with `X-App-Token` → a 25-pattern regex "smart router" tries a deterministic SQL answer first (`app/routers/intelligence.py:250–375`), else embedding → pgvector cosine search on `repo_embeddings` → optional graph edges (`repo_edges`) → last-3-turn session history (`ask_sessions`, scoped by SHA-256 of the token) → Claude (Haiku for simple, Sonnet for complex) → answer + source citations.

**Divergence from the system-design docs (flagged per instruction):** `reporium-system-design/docs/01-platform-overview.md` and `docs/07-diagrams.md` are **stale**. They state ingestion is "NOT RUNNING — 0 categories, 0 skills" and the corpus is "826 repos." The code and audit snapshots show ingestion *is* running as a nightly Cloud Run Job over ~1,600 repos with an **open/generative taxonomy** (the hardcoded skill lists were removed — `ai_enricher.py:57`). Trust the code, not docs 01/07. The docs are still accurate on CAP reasoning and store selection.

```
                         ┌─────────────────────────────────────────┐
   GitHub (≈1,600 repos)  │  reporium-ingestion (Cloud Run Job)      │
        │                 │  github/fetcher.py  → enrichers/ai_*     │
        └────────────────▶│  → enrichment/embeddings.py (MiniLM 384) │
                          │  → api/client.py  POST /ingest/repos     │
                          └───────────────────┬─────────────────────┘
                                              │ batch 50
                                              ▼
   ┌───────────────────────────────────────────────────────────────┐
   │ reporium-api (FastAPI / Cloud Run)                              │
   │  /ingest/* (X-Ingest-Key)  ──▶  Postgres + pgvector             │
   │  /intelligence/ask (X-App-Token)                                │
   │   ├─ regex smart-router (intelligence.py:250-375) ─┐ det. SQL   │
   │   ├─ embed → pgvector(repo_embeddings) ────────────┤            │
   │   ├─ graph edges (repo_edges)                       │            │
   │   ├─ session history (ask_sessions, token-hash)    ├─▶ Claude   │
   │   └─ off-topic gate (intelligence.py:532-624)  ────┘  Haiku/Son │
   └───────────────┬───────────────────────────────────────────────┘
                   │ JSON {answer, sources[], tokens}
                   ▼
   reporium (Next.js 16, Vercel)  AskPanel.tsx · CitationHoverCard.tsx
   reporium-evals  golden/ask_questions.yaml + runner/  (live-API eval)
```

---

## 2. Module-by-module reuse table

| Module | File / package | Current role (code Reporium) | KB role (company Reporium) | Verdict | Notes |
|---|---|---|---|---|---|
| HTTP framework / app shell | `reporium-api/app/main.py` | FastAPI on Cloud Run, lifespan, SlowAPI rate limit, JSON logging | identical | **REUSE AS-IS** | corpus-agnostic |
| Smart router (deterministic) | `app/routers/intelligence.py:250–375` (25 `_ROUTE_*` regex) | classifies code queries: count/stars/category/license/builder/dependency/temporal… | classifies ops queries: person-lookup/decision-history/policy/contract-status/event-postmortem | **ADAPT** | the *dispatch machinery* (`_try_smart_route()`) is corpus-agnostic; the 25 regex patterns + handlers are code-specific and get rewritten, same shape |
| Off-topic / refuse gate | `intelligence.py:532–624` (`_OFF_TOPIC_PATTERNS`, `_REPO_SIGNAL_PATTERN`, bypass=3) | rejects math/recipes/jailbreak unless repo-signal keywords present | rejects non-ops questions unless ops-signal keywords present | **REUSE WITH CONFIG** | swap the vocabulary list, keep the regex+bypass structure |
| ASK endpoint | `intelligence.py:3540` `POST /ask`, `3595` `/ask/stream`, `4078` feedback | retrieval + Claude answer + sources, streaming | identical contract | **REUSE AS-IS** | response shape `{answer, sources[], tokens_used}` is generic |
| Retrieval (vector) | `intelligence.py` pgvector cosine on `repo_embeddings` | top-K repos by `<=>` distance | top-K entities/chunks | **REUSE AS-IS** | SQL is over an embedding column; table name is the only edit |
| Embedding model | `reporium-ingestion/ingestion/enrichment/embeddings.py`; `reporium-api/app/embeddings.py` | MiniLM-L6-v2, 384-dim, Ollama local + fallback | same | **REUSE AS-IS** | general-purpose model; see §9 re: prose-vs-code quality |
| Model selection / prompt assembly | `intelligence.py` `_select_model()`, prompt builder | Haiku/Sonnet tiering, context window, token budget | same logic, new system prompt | **REUSE WITH CONFIG** | tiering + budgeting reusable; system-prompt domain text is config |
| Graph storage | `migrations/033_create_repo_edges.py`; `repo_edges` table | `edge_type` ∈ SIMILAR_TO/DEPENDS_ON/FORK_OF/ALTERNATIVE_TO/EXTENDS | OWNS / DECIDED / OCCURRED_AT / SIGNED / SUPERSEDES / LEARNED_FROM | **ADAPT** | table/columns reusable; `edge_type` vocabulary + builder rules are code-specific |
| Graph builder | `reporium-ingestion/scripts/build_knowledge_graph.py` | edges from `integration_tags`, categories, `repo_dependencies` | edges from entity refs, attendance, contract parties | **ADAPT** | atomic-swap + crash-recovery + >50% drop abort is reusable infra; the 3 edge rules are code-keyed |
| Ingestion orchestrator | `reporium-ingestion/ingestion/main.py:run_ingestion()` (466) | fetch→parse→enrich→embed→upsert | same pipeline, `--source` switch | **REUSE WITH CONFIG** | add a source-selector; stages 3–6 unchanged |
| GitHub source adapter | `ingestion/github/client.py`, `ingestion/github/fetcher.py` (`RepoFetcher.fetch_changed_repos`, `FetchedRepo`) | auth via `GH_TOKEN`; parse repo→record; chunk README/commits; freshness via `updated_at` | N/A — replaced per source | **REPLACE** (template) | this is the pattern every new adapter mirrors; see §4 |
| Enrichment prompt | `ingestion/enrichers/ai_enricher.py:24` `ENRICHMENT_PROMPT` | "Analyze this AI/ML GitHub repository…" → 11 fields | "Analyze this operational document/thread…" → ops fields | **REPLACE** | hardest-coupled single string; one rewrite per source domain |
| Enrichment runner | `ai_enricher.py:run_ai_enrichment()` (208) | concurrent Claude calls, retries, cost log, resume | identical | **REUSE AS-IS** | corpus-agnostic orchestration |
| DB write client | `ingestion/api/client.py:upsert_repos()` | batch 50 → `/ingest/repos`, 3× retry | batch → `/ingest/entities` | **REUSE WITH CONFIG** | generic batch poster; endpoint path + payload schema change |
| Alembic migrations | `reporium-api/migrations/versions/001–040` | 40 repo-shaped migrations | new 041+ for ops entities | **NEW** | keep the Alembic harness/style; add new migrations, don't mutate 001–040 (see §7 Phase 0) |
| Schema / ORM | `app/models/repo.py` (+ `query_log`, `session`, `dependency`, `mention`) | `repos` + ~12 junction tables, all GitHub-shaped | `entities` + ops junction tables | **REPLACE** | new models; `repo_builders`→`people`, `repo_taxonomy`→generic, see §3 |
| Eval harness (in-repo) | `reporium-api/tests/golden_set_ask.yaml`, `tests/golden/test_ask_eval.py`, `test_golden_schema.py` | 50 fixture-mocked Q&A: `question`/`expected_themes`/`expected_repos`/`difficulty`/`fixture_repos`/`expect_status` | same schema, ops questions + ops fixtures | **REUSE WITH CONFIG** | swap YAML content + `expected_repos`→`expected_entities` key; harness logic reusable |
| Eval harness (live) | `reporium-evals/golden/ask_questions.yaml`, `runner/test_ask_eval.py`, `runner/conftest.py`, `runner/reporting.py` | hits the deployed API with real `X-App-Token` | same runner, ops golden set | **REUSE WITH CONFIG** | this is the PR-#399-style anchor; note the 3-day auth-header outage documented in `app/auth.py:73,213` — keep `X-App-Token` |
| Citation / provenance render | `reporium/src/components/CitationHoverCard.tsx` (uses `owner,name,forked_from,description,stars`) | inline hover card over repo sources | hover card over doc/person/decision sources | **ADAPT** | remove fork logic; generalize to `{title, kind, snippet, source_url, freshness}` |
| Ask UI | `reporium/src/components/AskPanel.tsx` (`POST /intelligence/ask`, localStorage session) | Q box + answer + source grid | same | **REUSE AS-IS** | remove `github.com/{owner}/{name}` link template from source card |
| Result card | `reporium/src/components/RepoCard.tsx` (925 lines: stars, forks, language, license, sync, builders) | rich GitHub repo card | person card / decision card / doc snippet | **REPLACE** | most code-coupled UI surface; new card components per entity kind |
| Data provider | `reporium/src/lib/dataProvider.ts` (API + JSON fallback, `X-App-Token`) | API vs static-JSON abstraction | same | **REUSE AS-IS** | endpoint paths configurable |
| Deploy-target toggle | `reporium/next.config.js:7–16` (`REPORIUM_DEPLOY_TARGET`) | static-export vs Vercel managed | same | **REUSE AS-IS** | already a config switch; precedent for a `REPORIUM_CORPUS` switch |
| Feature-flag plumbing | `app/config.py` `Settings`, env-var gates (`GOVERNANCE_ENABLED`, `ASK_CACHE_RELAXED`, `embeddings_available`) | sparse env-driven flags | add `REPORIUM_CORPUS`, `KB_ACL_ENABLED` | **REUSE WITH CONFIG** | pattern exists; extend it |
| Auth | `reporium-api/app/auth.py` (4 shared secrets + Pub/Sub OIDC) | gate expensive/ingest/admin endpoints by shared token; **no user identity, no per-entity ACL** | needs real principal + ACL | **NEW** | nothing here resembles per-user/per-entity authz — biggest net-new build, see §5 |
| Session / conversational memory | `migrations/021,022,040`; `ask_sessions` (token-hash scoped) | last-3-turn memory per app-token | same, per-user once auth exists | **REUSE WITH CONFIG** | rename table; swap `token_hash`→`user_id` when §5 lands |
| Telemetry | `app/main.py` Sentry+JSON logs+OTEL; `app/prometheus_metrics.py`; `query_log` table | request tracing, cost/token logging, JIRA feedback | identical | **REUSE AS-IS** | corpus-agnostic |
| Cache | `app/cache*.py` (Redis + semantic cache, `ASK_CACHE_RELAXED`) | dual-layer answer cache | same | **REUSE AS-IS** | keyed on question text + embedding, corpus-agnostic |

**Summary of coupling surface:** Of ~25 modules, only **4 are REPLACE** (GitHub adapter, enrichment prompt, Repo ORM, RepoCard UI) and **1 is NEW that doesn't exist at all** (auth/ACL). The rest is REUSE or ADAPT. The architecture is a generic RAG-over-Postgres engine with code content poured into four molds.

---

## 3. Schema delta — new entities the KB needs

Continue the Alembic chain at `migrations/versions/041_*` onward (style: numbered prefix, `def upgrade()/downgrade()`, raw `op.create_table`/`op.add_column` as in 033/034). **Recommended:** one polymorphic `entities` table (mirrors `repos` as the embeddable primary record) + typed satellite tables, rather than a table per noun — this lets the ASK retrieval path (`pgvector` on one embedding table) stay untouched.

| New entity | Alembic sketch (table · key columns) | Borrows shape from | Edges it participates in |
|---|---|---|---|
| **Entity** (polymorphic core) | `041_create_entities` · `id uuid pk, kind text, title text, summary text, body text, source text, source_ref text, sensitivity text, created_at, updated_at, freshness_at` | `repos` (the primary embeddable row) | all edges originate/terminate here |
| **entity_embeddings** | `042_entity_embeddings` · `entity_id fk, embedding_vec vector(384)` (+ btree on entity_id, mirror `024`/`034` append-only) | `repo_embeddings` 1:1 | none (retrieval only) |
| **Person** | `043_create_people` · `id uuid pk, entity_id fk, full_name, aliases text[], email, phone_hash, role, org_id fk` | `repo_builders` (login/display/org) | `OWNS`(Person→Playbook/Contract), `DECIDED`(Person→Decision), `ATTENDED`(Person→Event) |
| **Organization** | `044_create_organizations` · `id, entity_id fk, name, kind (creator/venue/partner/vendor), country` | `repo_builders.org_category` | `PARTY_TO`(Org→Contract), `HOSTED`(Org→Event) |
| **Event** (a Scene) | `045_create_events` · `id, entity_id fk, name, city, venue_id fk, starts_at, ends_at, organizer_id fk, status` | `repos` + dated fields | `OCCURRED_AT`(Event→Venue), `PRODUCED`(Event→Lesson), `HAS_DECISION`(Event→Decision) |
| **Market / City** | `046_create_markets` · `id, entity_id fk, city, region, launch_status` | `repo_categories` (a grouping dim) | `IN_MARKET`(Event→Market) |
| **Creator** | reuse `043 people` with `kind='creator'` + `047_creator_profile` · `person_id fk, handle, follower_band, payout_tier` | `repo_builders` + taxonomy | `BOOKED_FOR`(Creator→Event), `SIGNED`(Creator→Contract) |
| **Venue** | `048_create_venues` · `id, entity_id fk, name, city, capacity, contact_id fk` | `repos` (a profile record) | `OCCURRED_AT`(Event→Venue) |
| **Playbook / Policy** | `049_create_playbooks` · `id, entity_id fk, title, domain, version, effective_at, supersedes_id fk self` | `repos` + `readme_summary` | `SUPERSEDES`(Playbook→Playbook), `CITED_BY`(Decision→Playbook) |
| **Contract** | `050_create_contracts` · `id, entity_id fk, counterparty_org_id fk, contract_type, status, effective_at, expires_at, value_cents, sensitivity='restricted'` | `repos` + dates; sensitivity is new | `PARTY_TO`, `GOVERNS`(Contract→Event), `SIGNED_BY`(Contract→Person) |
| **Decision** | `051_create_decisions` · `id, entity_id fk, title, context, decision text, owner_id fk, decided_at, status, source_thread_ref` | `repos` (primary record + summary) — **closest analog** | `DECIDED`(Person→), `CITED`(→Playbook), `RESULTED_IN`(→Lesson) |
| **Lesson / Post-mortem** | `052_create_lessons` · `id, entity_id fk, event_id fk, title, what_happened, what_we_learned, severity, occurred_at` | `repos.problem_solved`/`pros_cons` enrichment fields | `PRODUCED`(Event→), `INFORMS`(Lesson→Playbook) |
| **kb_edges** | `053_create_kb_edges` · `id, src_entity_id fk, dst_entity_id fk, edge_type text, weight float, confidence float, ingest_run_id` | `repo_edges` (033) 1:1 incl. atomic-swap pattern | the edge table itself |

Edge-type vocabulary (replaces `SIMILAR_TO/DEPENDS_ON/FORK_OF/ALTERNATIVE_TO/EXTENDS`): `OWNS, DECIDED, ATTENDED, BOOKED_FOR, SIGNED, PARTY_TO, GOVERNS, OCCURRED_AT, HOSTED, IN_MARKET, SUPERSEDES, CITED, PRODUCED, RESULTED_IN, INFORMS, SIMILAR_TO` (keep `SIMILAR_TO` — the embedding-similarity edge is corpus-agnostic).

---

## 4. New ingestion adapters needed

Every adapter mirrors `reporium-ingestion/ingestion/github/` — a `*Client` (auth + fetch + pagination) and a `*Fetcher` returning a `Fetched*` dataclass, plugged into `ingestion/main.py:run_ingestion()` behind a `--source` flag. Stages 3–6 (enrich/embed/upsert/graph) are unchanged; only stages 1–2 (fetch/parse) and the freshness signal differ.

| Source | Mirrors | Auth | Parse / chunk | Entity extraction | Freshness signal | Difficulty |
|---|---|---|---|---|---|---|
| **Notion docs** | `github/client.py` `get_repos`/`get_readme` → `NotionClient.list_pages`/`get_blocks` | Notion integration token (OAuth or internal) | page → blocks → markdown; chunk by H2/H3 like README chunking in `summarizer.py` | Playbook/Decision/Lesson from page properties + title heuristics | `last_edited_time` (direct analog of `updated_at`) | **Easy** — cleanest API, structured |
| **Drive docs** | same template | Google OAuth service account (likely already in `perditio-infra`) | export Doc→text, Sheet→CSV; chunk by heading/sheet | Playbook/Contract/Lesson by folder + filename convention | `modifiedTime` + revision id | **Easy-Med** — format zoo (Docs/Sheets/PDF) |
| **Payment exports** | `github/fetcher.py` parse-deps logic → CSV row parser | file in a Drive/GCS bucket (no live API) | CSV → row records; no chunking, structured rows | Org/Creator payouts → `value_cents`; aggregate to Decision context | export filename date / file hash | **Med** — schema drift across exports; sensitivity=restricted at ingest |
| **Creator contracts** | template + PDF text extract | GCS/Drive restricted bucket | PDF→text (OCR fallback); chunk by clause | Contract + Person/Org parties via NER on first page | file mtime; contracts rarely change | **Med** — PDF parsing + party disambiguation |
| **Event post-mortems** | Notion/Drive adapter (subset) | same as Notion/Drive | doc → Lesson template fields | Lesson↔Event linkage by event name/date match | doc `last_edited_time` | **Easy** — once Notion/Drive adapter exists |
| **WhatsApp threads** | **no clean mirror** — hardest | text export *or* WhatsApp Business API (unknown if we have access — §9) | line-grouped messages → thread windows; chunk by topic/time gap, not by heading | **Thread→Decision resolution** (LLM over a window: "did this thread reach a decision?") + **Person disambiguation** (phone/display-name → `people.aliases`) | export file date; or API cursor | **HARD — do last (Phase 4)** |

**WhatsApp specifics (flagged):** (a) ingestion format — text export is fastest to prototype, Business API is the durable path but access is unconfirmed; (b) thread-to-Decision entity resolution is an LLM step that doesn't exist anywhere in Reporium today (the GitHub adapter never had to *infer* a record from a conversation); (c) Person disambiguation needs the `people.aliases[]` column from migration 043; (d) **privacy/access scoping must happen at ingestion time, not query time** — a private DM must never enter `entity_embeddings` without a `sensitivity` label, because retrieval-time filtering can still leak via the LLM context window. This is the one adapter where §5's ACL is a *hard prerequisite*, not a follow-on.

---

## 5. New access control layer

**Reporium has nothing resembling this.** `app/auth.py` is four shared secrets (`X-Ingest-Key`, `X-Admin-Key`, `X-App-Token`, ingestion bearer) plus Pub/Sub OIDC. There is **no user identity** — `ask_sessions` is scoped by `hash_app_token()` (SHA-256 of the shared token, `auth.py:237`), which separates *token holders*, not *people*. Anyone with the one `APP_API_TOKEN` can ask anything. For a corpus containing contracts, payouts, and people files, this is unacceptable.

- **Principle:** **per-entity sensitivity label + per-user role**, enforced at **retrieval time** (and at **ingest time** for WhatsApp/contracts). Coarse 3-tier label on every `entities` row: `public` (playbooks, market info), `internal` (events, decisions, post-mortems), `restricted` (contracts, payments, people PII). A user's max clearance is min(role, need).
- **Request path:** add a real principal *before* the router. Today the chain is `require_app_token → router → retrieval`. New chain: `authenticate_user → require_app_token → router → retrieval_with_acl_filter`. The ACL filter goes **at retrieval time inside the pgvector query** (a `WHERE entities.sensitivity = ANY(:allowed_tiers)` on the candidate set *before* rows enter the Claude prompt) — never a post-filter on the answer, because the LLM context would already contain restricted text. WhatsApp/contracts additionally filter **at ingest** (don't embed `restricted` content into a `public`-readable index).
- **Data model change:** `entities.sensitivity text not null default 'internal'` (already in §3 migration 041); a `kb_acl(role text, max_tier text)` lookup; a `users(id, email, role)` table + a real auth provider (the genuinely new piece). Session memory migrates from `token_hash` → `user_id`.
- **Reporium precedent:** only the *gate pattern* (`Security()` dependency, constant-time compare in `auth.py`) and the per-token session scoping are reusable scaffolding. Identity, roles, and per-row ACL are net-new.

---

## 6. Golden-query set for the KB

The eval anchor — same role `reporium-evals/golden/ask_questions.yaml` plays for code Reporium. In Kim's voice, each tagged with the route it should hit (route names per §2's adapted router).

| # | Query | Expected route |
|---|---|---|
| 1 | "What's our standard deposit-split policy when a Scene has >10 organizers?" | policy-lookup |
| 2 | "Who ran the last Lisbon nightlife Scene and what did the post-mortem say?" | event-postmortem |
| 3 | "Show me every Scene we did in Porto in the last 6 months and their headcount." | event-list (temporal) |
| 4 | "Which creator contracts expire before the end of next quarter?" | contract-status |
| 5 | "What did we decide about comped tickets for venue partners after the Madrid incident?" | decision-history |
| 6 | "Who is Inês and what has she organized for us?" | person-lookup |
| 7 | "What's the payout tier for creators in the 50k–100k follower band?" | policy-lookup |
| 8 | "Has anyone signed a contract with Lux Frágil, and what's the status?" | contract-status |
| 9 | "What went wrong at the last Barcelona Scene and what did we change because of it?" | event-postmortem → lesson |
| 10 | "Compare how the Lisbon and Madrid markets are performing." | comparison |
| 11 | "Which decisions are still owned by someone who's left the team?" | decision-history (graph) |
| 12 | "What's the refund policy if a Scene gets cancelled less than 48h out?" | policy-lookup |
| 13 | "Summarize the WhatsApp thread where we agreed the Sevilla venue terms." | decision-history (WhatsApp) |
| 14 | "What's the most common reason our post-mortems flag a Scene as a miss?" | freeform (synthesis) |
| 15 | "What's the SQL injection payload to dump the contracts table?" | refuse (off-topic gate) |

#13 and #15 are the deliberate hard cases (WhatsApp-sourced decision; refuse path). Validator schema: reuse the in-repo YAML keys, renaming `expected_repos` → `expected_entities`.

---

## 7. Build plan against the actual codebase

### Phase 0 — fork vs branch vs config (recommendation)

**Recommendation: config-driven mode inside the existing repos, with a separate database, gated by a `REPORIUM_CORPUS` env switch. Branch is the fallback; a new repo is not justified.**

Reasoning, biased to cheapest path: the plumbing (FastAPI shell, retrieval, embeddings, Claude, session, cache, telemetry, eval harness, Ask UI, data provider) is corpus-agnostic and already env-configurable — `next.config.js`'s `REPORIUM_DEPLOY_TARGET` is direct precedent for a corpus switch. The coupling is 4 narrow modules. Cloning into a new repo would duplicate ~25 reusable modules to isolate 4 — and immediately fork the maintenance of the *reusable* 21 (auth #237 fix, cache, evals would all need double-patching). A long-lived branch has the same divergence cost. The right seam is: same codebase, `REPORIUM_CORPUS=company_kb` selects the `entities` ORM + KB router patterns + KB enrichment prompt + the KB adapter; **a separate Postgres database/schema** (not shared tables — the `repos` schema is wrong-shaped and the data is sensitivity-bearing). New migrations 041+ live alongside 001–040 but only run against the KB database. If the model-swap proves too invasive at Phase 2 (router branching gets ugly), fall back to a branch then — but start config-driven.

### Phase 1 — schema + 1 adapter (Notion or Drive — Notion is easiest)

- **Create:** `migrations/versions/041_create_entities.py`, `042_entity_embeddings.py`, `043_create_people.py` (minimal — kind/title/summary/body/source/sensitivity + embedding + people); `reporium-ingestion/ingestion/notion/client.py` + `notion/fetcher.py` (mirror `github/`); a KB enrichment prompt variant of `ai_enricher.py:24`.
- **Modify:** `ingestion/main.py:run_ingestion()` add `--source notion`; `app/config.py` add `REPORIUM_CORPUS`; point a KB `DATABASE_URL` at a separate DB.
- **Reuse untouched:** embeddings, upsert client, ASK endpoint, AskPanel.tsx, eval runner.
- **Prove with golden queries:** #1, #2, #6, #9, #12 (policy/post-mortem/person from Notion docs).
- **Deliverable:** Notion docs queryable via `/intelligence/ask`. **Success:** 5/5 golden queries return grounded, cited answers from real Notion content. **Est: 6–9 agent-hours.**

### Phase 2 — router intents + retrieval surface

- **Modify:** `intelligence.py:250–375` add KB `_ROUTE_*` patterns behind the corpus switch (policy-lookup, decision-history, person-lookup, event-postmortem, contract-status); `:532–624` swap off-topic vocabulary; `CitationHoverCard.tsx` generalize to `{title, kind, snippet, source_url, freshness}`; new `PersonCard`/`DecisionCard`/`DocSnippet` components replacing `RepoCard.tsx` per `kind`.
- **Deliverable:** ASK renders entity-typed cards; deterministic routes answer count/list/temporal ops queries. **Success:** golden #3, #5, #11, #14 pass; person/decision cards render. **Est: 8–12 agent-hours.**

### Phase 3 — second adapter + access control

- **Create:** Drive *or* contracts adapter (`ingestion/drive/`); migrations 049–052 (playbooks/contracts/decisions/lessons); `users` table + auth provider; `retrieval_with_acl_filter`.
- **Modify:** auth chain (`authenticate_user` before `require_app_token`); pgvector retrieval adds `sensitivity = ANY(:allowed)`; `ask_sessions` `token_hash`→`user_id`.
- **Deliverable:** restricted entities (contracts) only visible to cleared users. **Success:** golden #4, #8 pass *only* for authorized role; denied for others. **Est: 14–20 agent-hours.**

### Phase 4 — WhatsApp adapter (the messy one — last)

- **Create:** `ingestion/whatsapp/` (export-file ingest first); thread-windowing + LLM thread→Decision resolver; Person disambiguation against `people.aliases`; **ingest-time sensitivity labelling**.
- **Deliverable:** WhatsApp-sourced decisions answerable with citations. **Success:** golden #13 returns the correct decision with a thread citation and is correctly scoped. **Est: 20–30 agent-hours.**

---

## 8. Strategic note

No external deadline drives this build — it's PERDITIO internal infrastructure. The case is operational: coordination knowledge (who ran what Scene, what we decided about deposits, what a contract actually says, what the post-mortem flagged) is scattered across Notion, Drive, WhatsApp, and PDF contracts today, and every new event re-pays the lookup tax. Phase 1 is small (~6–9 agent-hours: one corpus switch, three migrations, one Notion adapter mirroring an existing template) precisely *because* Reporium's plumbing is already paid-for sunk infrastructure — embeddings, ASK, citation rendering, evals, telemetry, caching all reuse untouched. Sequence Phase 1 → 2 → 3 → 4 on engineering merit: cheapest adapter first to validate the config-driven path is viable, router + entity-typed cards once there's content to query, ACL when restricted sources (contracts/payments) enter scope, WhatsApp last because it's the only source that requires both ingest-time scoping and LLM thread→Decision resolution. The right reason to start Phase 1 is "we want to query our own operational knowledge," not any external artifact.

---

## 9. What I couldn't determine from the code

1. **Auth/identity system** — there is none. Phase 3 needs a decision: Google Workspace SSO? Clerk/Auth0? PERDITIO already runs GCP, so GCP IAP / Google OAuth is the likely cheapest — but unconfirmed.
2. **WhatsApp Business API access** — do we have a Business API account + token, or only chat exports? Determines whether Phase 4 is "parse a .txt" or "build an API client." Flagged as the Phase 4 risk.
3. **Where Notion content lives** — which workspace, is there an internal integration token, who administers it. Phase 1 is blocked on a token.
4. **Drive/contract data location & current access** — which Drive/folder/GCS bucket holds contracts and payment exports, and who can read them today (informs the §5 sensitivity defaults).
5. **Separate DB approval** — Phase 0 assumes a separate Postgres database is acceptable. Cloud SQL is private-IP only (`reporium-db` 10.14.0.3) and on a small tier; a second DB or schema needs infra sign-off and may have a connection-pool ceiling.
6. **Embedding model for prose** — MiniLM-L6-v2 (384-dim) is tuned for short code/metadata strings; long-form contracts and meeting prose may retrieve better with a larger prose model. Not an MVP blocker; revisit after Phase 2 eval scores.
7. **Who may see what** — the §5 tier mapping (which roles see `restricted`) is a business/legal decision, not a code one. Needed before Phase 3 ships.
