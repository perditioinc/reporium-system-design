# 09 - Navigating Ambiguity

How to make decisions when the right answer is not obvious.

---

## The Reversibility Framework

Every decision has a reversal cost. Use that cost to determine how much time to spend deciding.

**Cheap to reverse (hours to days):**
- Which database to use (change a connection string, run migrations)
- Which cache provider (swap Redis for Memcached, same interface)
- Deployment platform (Cloud Run to App Engine, same container)
- File format (JSON to YAML, write a converter)

For cheap-to-reverse decisions: decide quickly, ship, measure, adjust. The cost of being wrong is low. The cost of deliberating is high.

**Expensive to reverse (weeks to months):**
- Data model and schema design (every consumer depends on it)
- Programming language (rewrite everything)
- API contract (external consumers depend on it)
- Authentication system (security implications of migration)

For expensive-to-reverse decisions: invest time upfront. Write design docs. Get review. Prototype before committing.

**Reporium examples:**
- Neon vs Cloud SQL: cheap to reverse (change connection string). Decision: start with Neon, switch if needed. Took 10 minutes to decide.
- Partitioned JSON vs single file: moderate to reverse (migration script). Decision: partition early, before consumers depend on the single-file format. Took 1 hour to decide.
- Data model (13 tables): expensive to reverse (API depends on schema). Decision: designed carefully, reviewed against query patterns. Took a full day.

---

## Prioritization Under Constraints

With limited time and a single maintainer, everything cannot be built at once. The prioritization order:

1. **Data integrity first.** If the sync is wrong, everything downstream is wrong. forksync and reporium-db were the first priority.
2. **Observability second.** SYNC_REPORT and LAST_RUN were added before any optimization. You cannot improve what you cannot measure.
3. **Performance third.** The v1-to-v2 forksync improvement (14 minutes to 143 seconds) only happened after we had reliable sync and measurement.
4. **Enrichment last.** AI categorization depends on clean data from a reliable pipeline. Running it on broken data produces garbage.

This order is not arbitrary. Each layer depends on the one below it. Skipping ahead (e.g., building enrichment before sync is reliable) creates technical debt that is expensive to fix.

---

## Cross-Team Collaboration

When working with engineers who own different parts of the system:

**Share ground truth, not opinions.** Instead of "I think forksync is fast enough," share the SYNC_REPORT: "143s, 792 repos, 1 error, 4,876 rate limit remaining."

**Document what does not work.** The platform overview includes a "What Is Not Yet Working" section. This prevents surprises and builds trust. If I hide the gaps, engineers discover them on their own and lose confidence in the rest of the documentation.

**Make decisions traceable.** Every decision in the decision log explains what we tried, what broke, and why we changed. When an engineer asks "why did you use Neon instead of Cloud SQL?" the answer is in doc 02, decision 5.

**Separate facts from plans.** Facts: "826 repos, 143s sync, 0 categories." Plans: "Add ingestion after 2 weeks of stable sync." Mixing these leads to confusion about what is real and what is aspirational.

---

## Saying No with Data

Sometimes the right decision is to not build something. Examples:

**"Should we add real-time sync?"**
No. The data shows 826 repos with a nightly pipeline. Real-time sync would require webhooks for all 826 repos, a persistent connection to GitHub, and a streaming architecture. The current users (portfolio, docs, search) do not need data fresher than 24 hours. The cost does not justify the benefit.

**"Should we move to a paid database now?"**
No. The data shows 124 API calls per sync cycle, 2.5% rate limit usage, and Neon free tier handling all queries. Moving to a paid tier solves a problem we do not have yet. When the monitoring shows we are approaching limits, we move.

**"Should we add multi-region deployment?"**
No. The API serves portfolio traffic, not production SLA-bound traffic. A single region (us-central1) with Cloud Run auto-scaling is sufficient. Multi-region adds cost and operational complexity for zero user benefit at current scale.

In each case, the answer is not "no, I do not want to." It is "no, and here is the data that supports waiting." The data makes the conversation about facts, not preferences.
