# 06 - Working with Engineers

Real examples of how I approach collaboration, communication, and technical decision-making.

---

## Measuring Before Claiming

On 2026-03-18, I ran a full audit of the Reporium platform. I did not estimate numbers or round them. I read them from the actual system.

The forksync SYNC_REPORT said: 143s duration, 792 repos checked, 50 concurrent, 1 error. Not 68 seconds (that was an earlier, smaller run). Not "about 2 minutes." Exactly 143 seconds, from the report the system generated.

The LAST_RUN file said: 9 API calls, 4,876 rate limit remaining. That means 124 calls consumed out of 5,000. I did not say "a few API calls." I said 9, because that is what the file said.

The API /stats endpoint and index.json both reported 826 repos. I checked both to make sure they agreed. They did.

reporium-ingestion showed 0 categories enriched and 0 repos with AI skills. I did not say "ingestion needs work." I said it is not running, the numbers prove it, and that is expected because we prioritized sync reliability first.

When I present numbers to engineers, they are verifiable. Every claim traces back to a file, an API response, or a log entry. This builds trust faster than any amount of explanation.

---

## The merge-upstream Discovery

The first version of forksync used the GitHub merge-upstream API. It returned HTTP 200 for every request. The logs looked clean. But forks were not actually syncing.

I did not assume the API was broken. I compared commit SHAs before and after the merge-upstream call. They were identical. The API was returning success without doing anything.

I brought this to the discussion with a specific reproduction case: "Here is the fork, here is the upstream SHA, here is the SHA after merge-upstream. They are the same." Not "I think merge-upstream is broken" but "here is the evidence that it does not work for our use case."

The fix was straightforward: switch to `gh repo sync`, which either works or returns non-zero. But the finding needed evidence, not opinion.

---

## The 2026-03-18 Audit

I audited every component of the platform on 2026-03-18. The purpose was to establish ground truth before making any plans.

Findings:
- 826 repos tracked (confirmed from two independent sources)
- 29 languages (from API /stats)
- forksync working: 143s, 792 checked, 1 error
- reporium-db working: 127.1s, 9 API calls
- reporium-ingestion not running: 0 enriched categories, 0 AI skills
- Neon database: 13 tables, pgvector enabled
- Redis: connected to forksync, not to API
- Pub/Sub: designed, not deployed

I documented what works and what does not work with equal detail. The temptation is to highlight the working parts and gloss over the gaps. But engineers need the full picture to make good decisions. If I hide the fact that ingestion is not running, someone might plan work that depends on enrichment data being available.

---

## Handling Pushback with Data

When I proposed switching from sequential to concurrent sync (Decision 2 in the decision log), the concern was rate limit exhaustion. "If you run 50 concurrent, you will blow through the rate limit."

I did not argue. I ran the concurrent sync and read the LAST_RUN file: 9 API calls, 4,876 rate limit remaining. That is 2.5% of the budget. I showed the numbers.

The concern was reasonable. The data resolved it. No debate needed.

This pattern repeats: concern is raised, I run the experiment, I show the measurements. Not "I think it will be fine" but "I ran it and here are the numbers."

---

## Navigating Ambiguity with the Reversibility Framework

When choosing between Neon and Cloud SQL (Decision 5), there was uncertainty about whether Neon's free tier would be sufficient long-term. Instead of trying to predict the future, I asked: "Is this decision reversible?"

Switching from Neon to Cloud SQL requires changing a connection string and running migrations. It is a few hours of work, not a rewrite. So we start with Neon ($0/month) and switch if we hit limits.

This is the reversibility framework: if a decision is cheap to reverse, make it quickly and learn from the result. If it is expensive to reverse (like choosing a programming language), invest more time upfront.

Most infrastructure decisions in Reporium are reversible. The database, the cache, the message queue, the deployment platform. The one thing that is not easily reversible is the data model. That is where we spend the most design time.
