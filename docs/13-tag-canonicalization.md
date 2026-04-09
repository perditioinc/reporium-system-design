# 13 - Tag Canonicalization

One decision about how integration tags from the AI enricher are normalized before they are used to build graph edges.

---

## Decision 13: Tag Vocabulary and Canonicalization

**Context:** The AI enricher produces `integration_tags` for each repo — a list of technologies, frameworks, and concepts the repo relates to. These tags drive `COMPATIBLE_WITH` edges in the knowledge graph: two repos that share a canonical tag are considered compatible. The enricher generates these tags as free-form text from the model's output.

**What we tried:** Using raw tags after lowercasing. A repo tagged `"LLM"` became `"llm"`. Another tagged `"large language model"` stayed `"large language model"`. A third tagged `"LLMs"` became `"llms"`. All three describe the same concept. Under raw-lowercase matching, none of them matched any of the others.

**What broke:** The `COMPATIBLE_WITH` edge graph was fragmented. Repos that were genuinely compatible — both using the same underlying technology — failed to receive edges because their tags happened to be worded differently. The model's output is inconsistent across runs: the same repo re-enriched on a different day might get different tag phrasings. Edges appeared and disappeared between runs for no semantic reason. The graph was noisy and incomplete.

We also saw the inverse problem: tags that were superficially similar but semantically distinct. `"web3"` and `"Web3 / DeFi"` look close under fuzzy matching but represent different scopes. A pure fuzzy-match approach collapsed things that should not be collapsed.

**Decision:** Implement a `canonicalize_tags()` module with a curated vocabulary of approximately 200 canonical tag names. The vocabulary covers the most common technology domains: model families, ML frameworks, deployment targets, data formats, programming paradigms, and integration patterns.

The canonicalization process works as follows:

1. Lowercase and strip the raw tag.
2. Check for an exact match in the vocabulary. If found, use it.
3. Run `difflib.get_close_matches(raw_tag, vocabulary, n=1, cutoff=0.82)`. If a match is found above the threshold, use the matched canonical name.
4. If no match is found, log the raw tag at DEBUG level (as an unmatched tag) and keep the raw tag as-is.

The raw tags are stored in a separate column `raw_integration_tags TEXT[]` so the original model output is preserved. The canonicalized tags go into `integration_tags TEXT[]`, which is what the graph build and the API use.

The same vocabulary file is maintained in both the ingestion repo and the API repo. Both import it from a shared constants module (copied at deploy time, not shared via package dependency — the repos are separate services). Divergence between the two vocabularies would cause the API to return tags that do not match the graph's edge labels.

**Tradeoff:** The threshold of 0.82 is empirical and was set after reviewing a sample of unmatched tags from several enrichment runs. It is not theoretically derived. Too high a threshold misses valid collapses: `"pytorch"` and `"PyTorch"` might score 0.80 and be kept separate. Too low a threshold creates false collapses: `"web3"` and `"Web3 / DeFi"` score around 0.75 and should remain distinct.

The threshold requires periodic review. We examine DEBUG log output for unmatched tags after each enrichment run and update the vocabulary when a new technology name appears frequently. The vocabulary is hand-curated, not auto-generated — this is intentional. Automated vocabulary expansion risks silently introducing bad canonical names.

The ~200-name vocabulary does not cover every possible tag the model might generate. Tags outside the vocabulary pass through as raw strings. This means some tags remain uncanonicalized, which is preferable to an incorrect canonical mapping.

---
