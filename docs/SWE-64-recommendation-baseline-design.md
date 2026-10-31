# SWE-64 — Recommendation Baseline Algorithm Design

**Project:** SWE Group 03 — E-commerce Recommendation System  
**Status:** Initial algorithm design; implementation and evaluation pending  
**Catalog scope:** 1,500 selected products  
**Dependencies:** [SWE-62 Data Requirements](SWE-62-recommendation-data-requirements.md), [SWE-63 Architecture](SWE-63-recommendation-architecture.md)  
**Last updated:** 2026-10-31

## 1. Problem statement

For an input product `p`, rank other catalog products by product-content similarity and return the Top-K candidates. The system must work **without** user-item interaction histories. The MVP is a **product-to-product content-based recommender**, not personalized recommendation and not collaborative filtering.

The present V4.1 files are Amazon-derived candidates; the current selected subset is **1,500 products**, but the exact subset has not been uploaded for audit. Every reported score below is an illustration or evaluation definition, **not a benchmark result**.

## 2. Selected baseline

**Algorithm:** TF-IDF vectorization + cosine similarity, with optional category-based candidate restriction.

### 2.1 Feature generation (baseline B0)

For each product, construct one text document from:

1. `name` (required);
2. `description` (optional; use an empty string if absent).

Normalize whitespace and case, but keep distinguishing product model strings (e.g., CPU model and storage capacity). Fit a single TF-IDF vocabulary over the selected catalog. Use a deterministic product-ID order; store both matrix row indices and source/Backend ID mappings.

**Suggested initial configuration** (subject to measured comparison): `lowercase=True`, `ngram_range=(1, 2)`, `sublinear_tf=True`, `norm='l2'`. Do not apply broad numeric-token stripping: model numbers, RAM and storage sizes carry meaning in electronic products. Tune `min_df` only after checking vocabulary loss on the small 1,500-item dataset.

Category is used as a **candidate filter**, not blindly treated as a correctness guarantee, because some source category labels are demonstrably incorrect. If category has not been reviewed, report this limitation; do not claim strict category precision.

### 2.2 Similarity score

For TF-IDF vectors `x_i` and `x_j`:

\[
\operatorname{sim}(i,j) = \frac{x_i \cdot x_j}{\lVert x_i \rVert_2\lVert x_j \rVert_2}
\]

With L2-normalized nonzero vectors, the cosine similarity equals their dot product. Rank candidates by descending similarity; use a stable ID as a deterministic tie-breaker. This score measures lexical overlap, **not purchase likelihood** or product quality.

### 2.3 Recommendation algorithm (pseudocode)

```text
recommend_similar(query_product_id, K):
    validate K in [1, 20]
    resolve query_product_id to an indexed row
    if not indexed: return NOT_FOUND

    candidate_ids = all indexed products except query_product_id
    if reviewed category constraint is enabled:
        candidate_ids = same-approved-category candidates

    scores = cosine(query_vector, candidate_vectors)
    rank by (-score, stable_candidate_id)
    remove exact duplicates and invalid candidate IDs
    return up to K ranked IDs and similarity scores
```

For production serving, indexed products must have an approved mapping to Backend `product_id`; Backend checks publication/availability/price after retrieval. A missing mapping is not a reason to return `parent_asin` as if it were a Backend ID.

## 3. Scope of the 1,500-product dataset

The input must be a **named, reproducible selection** of 1,500 distinct `parent_asin` values joined across V4.1 product/specification files. The uploaded historic dataset has 10,000 rows, so the target subset must be explicitly identified before implementation and evaluation.

**Required validation:** selected count, unique IDs, join integrity, nonempty names, category distribution, missing descriptions, missing/`UNVERIFIED` specs, unresolved brands and unapproved commercial fields. Export an audit report and an artifact manifest containing dataset checksums; do not invent statistics for the selected sample.

**Category strategy:** Evaluate the actual selected categories first. If Laptop, Smartphone or Tablet are included, they are reasonable candidates for specification ablation experiments, but no category's presence or count in the 1,500 selection is assumed.

## 4. Staged experiments

| Version | Feature set | Goal | Status |
| --- | --- | --- | --- |
| **B0** | Name + description, TF-IDF/cosine; optionally reviewed category filter | Obtain a simple reproducible lexical baseline. | Designed, not executed. |
| **B1** | B0 + resolved brand and registry-compatible specification text | Test whether available structured metadata improves relevance. | Proposed experiment. |
| **B2** | B1 + typed numerical specification comparisons (category-specific) | Better represent RAM/storage/display differences than raw tokens can. | Optional follow-up; not MVP prerequisite. |

For B1/B2, preserve missingness indicators and evidence. V4.1 specification values are `UNVERIFIED`; do not treat them as guaranteed truth. The following candidate registry keys were observed in the original V4.1 source: `cpu_family`, `cpu_model`, `gpu_model`, `physical_ram`, `installed_storage_gb`, `internal_storage`, `display_diagonal`, `display_resolution`, `battery_capacity_mah`. **Key applicability differs by category**. The 1,500 selection may have fewer keys.

## 5. Evaluation plan (offline)

Without interaction labels, metrics such as purchase conversion, CTR, NDCG from clicks, collaborative-filtering Recall@K, and model accuracy percentages **cannot be validly reported** for this dataset alone.

### 5.1 Automated correctness checks

- **Input validity:** fail or report invalid/missing IDs, empty text, malformed specifications, and duplicate source keys.
- **Self-match rate:** query product never appears among its own recommendations (required: zero).
- **Duplicate result rate:** no duplicated returned product IDs (required: zero).
- **Top-K behavior:** return 0 to `K` items, respecting restricted candidate pools.
- **Determinism:** repeated calls against the same artifact and query return identical ordering/scores.
- **Score validity:** scores finite and within the expected cosine range (allow small floating-point tolerance).
- **Coverage:** percentage of valid indexed source products for which the method returns at least one recommendation; report by category.
- **Latency:** measure p50/p95 after warm-up on named hardware; do not claim an SLO without measured results.

### 5.2 Human relevance evaluation

After the actual 1,500-product subset is available:

1. Sample query products across represented categories (stratified sample with a fixed random seed; record the sample list).
2. For each query, generate Top-5 candidates from B0; use the same queries for B1/B2.
3. Ask two reviewers to label each query–candidate pair: `0` = unrelated, `1` = loosely related, `2` = functionally similar/substitutable. Include a note for category errors and variants.
4. Compute **Relevant@5** as the proportion of candidates receiving label `2` (state whether majority/adjudicated labels are used) and report distribution by category; also report disagreement between reviewers.
5. Compare B0 against B1/B2 **only on the same judged query set**. Report uncertainty and example failures rather than claiming an arbitrary percentage of "accuracy." 

A threshold for acceptable human relevance is a **team decision after a pilot labeling pass**, not a pre-existing measured result.

## 6. Important failure cases and mitigations

| Risk | Effect | Baseline mitigation |
| --- | --- | --- |
| Incorrect source category | Unrelated products may be compared or incorrectly excluded. | Review labels; report errors; avoid declaring category filter authoritative before approval. |
| Missing description | Weak lexical representation. | Use name-only fallback; track text coverage. |
| Missing or unverified brand/specification | B1/B2 biased toward richly described products. | Keep B0 independent; ablation-test optional fields; disclose missingness. |
| TF-IDF treats `8 GB` and `16 GB` lexically | Numerical similarity is poorly represented. | Keep B0 as baseline, explore typed numeric comparison in B2. |
| Duplicate or variant-like source records | Repetitive Top-K results. | Deduplicate exact IDs and report near-duplicates; do not assume candidate variant boundaries are approved. |
| Unknown/retired Backend product | Invalid recommendation. | Require approved ID mapping; Backend hydrates and filters at serving time. |
| Price/stock changes after indexing | Stale commerce output. | No price/stock in similarity model; Backend validates current state. |
| Amazon image/source-price permissions | Publishing risk. | Do not serve source media or unapproved Amazon prices. |

## 7. Expected implementation interfaces (design only)

Suggested separation:

```text
src/recommendation/
  prepare_data.py         # audited source join and text preparation
  baseline.py             # fit/load TF-IDF; top-k cosine retrieval
  evaluation.py           # deterministic checks and offline human review export
artifacts/recommendation/  # generated, versioned, usually gitignored
```

Each index build must save: input dataset SHA-256, ordered indexed IDs, feature configuration, package/runtime versions, fit timestamp, approval mode (`research` vs `production`) and reproducible evaluation seed. The repository's existing package layout takes precedence; these are illustrative paths, **not existing files**.

The intended production integration is the internal interface in SWE-63. This Jira task's specified expected deliverable is **Initial Algorithm Design**; model implementation, API deployment and measured evaluation are separately tracked follow-up work unless the team explicitly expands the scope.

## 8. Acceptance criteria and definition of done

**For the document-design deliverable:**

- [x] State recommendation objective, baseline algorithm and feature inputs.
- [x] Define similarity scoring, ranking, exclusion and tie behavior.
- [x] Document staged feature extensions and dataset risks.
- [x] Specify valid offline evaluation methodology and edge cases.
- [ ] Confirm categories and quality of the **actual** 1,500 selected records.
- [ ] Obtain team review of baseline design and evaluation rubric.

**For subsequent implementation (not falsely claimed complete):**

- [ ] Build a deterministic TF-IDF index from the audited 1,500-product subset.
- [ ] Produce reproducible Top-5 samples and automated correctness checks.
- [ ] Perform a labeled relevance evaluation; compare B0/B1 only if both are actually run.
- [ ] Integrate authorized Backend IDs and validate serving failure cases.

**Task status recommendation:** Initial algorithm design drafted; do not claim an executed baseline or completed evaluation until artifacts and results exist.
