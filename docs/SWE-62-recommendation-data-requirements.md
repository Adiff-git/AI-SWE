# SWE-62 — Recommendation Data Requirements

**Project:** SWE Group 03 — E-commerce Recommendation System  
**Status:** Draft for AI/Backend review  
**Dataset scope:** 1,500 selected products (current project scope; selection file not yet supplied for verification)  
**Source version:** Amazon catalog normalization V4.1  
**Related tasks:** SWE-63 (Architecture), SWE-64 (Baseline Design)  
**Last updated:** 2026-10-31

## 1. Objective and scope

Define the product metadata, optional user-behavior signals, data quality checks, and AI–Backend responsibilities necessary to design the first product recommendation feature.

**MVP use case:** Given a product, return a ranked list of similar products (content-based recommendation). **Deferred:** personalized, collaborative-filtering, and behavior-based popularity ranking until representative interaction data is available.

This document defines *requirements*, not proof that Backend APIs, event storage, or production product records currently exist.

## 2. Data sources and evidence

The supplied V4.1 source artifacts are:

| Artifact | Relevant role | Notes |
| --- | --- | --- |
| `catalog_products_v4_1.jsonl` | Source product records | Contains `parent_asin`, `name`, `category`, `description`, `brand_candidate`, `category_id`, `image_url_source`, `trace`, `status`, `variant_candidate` and unapproved source prices. |
| `catalog_specifications_v4_1.jsonl` | Technical specifications | Contains `parent_asin`, `technical_specifications.schema_version`, `technical_specifications.values`, `approval`, `evidence`, `review_issues`. |
| `catalog_candidates_v4.csv` | Original candidate metadata | Includes `features_json`, `amazon_categories_json`, `average_rating`, `rating_number`, and `review_status`. Research-only unless otherwise approved. |
| `README_v4_1.md` | Normalization contract | V4.1 keys follow the Backend v1 attribute registry; extracted specification values remain `UNVERIFIED`. |
| `normalization_summary_v4_1.json` | Legacy dataset audit | Describes the **original 10,000-record pool**, not the selected 1,500-record subset. |
| `specification_comparison_v4_1.json` | Legacy vs V4.1 analysis | Comparison numbers are likewise for the original pool; conflict reductions do not imply verified correctness. |

**Important distinction:** The uploaded JSONL/CSV files contain 10,000 source rows each, while the current project is expected to use 1,500 selected products. A new subset manifest and fresh subset statistics are **pending**. Do not reuse old counts/coverage rates as measurements of the 1,500-product subset.

### 2.1 Source identification

- `parent_asin` is the external Amazon **source identifier** and join key across supplied product/specification artifacts.
- `product_id` is the canonical identifier to be assigned/confirmed by Backend; do **not** assume it equals `parent_asin`.
- `variant_id` is a distinct Backend identifier when a sellable variant exists. V4.1 `variant_candidate` does not establish a verified variant.
- The recommended MVP operates at **product level**, with inventory and sellable-variant selection controlled by Backend.

## 3. Functional data requirements

### 3.1 Content-based similar products (MVP)

The recommender requires a stable identifier and sufficient product text to calculate similarity. A product may still be eligible for a text-only recommendation when some attributes are missing.

| Logical field | V4.1 source | Requirement | AI use and constraint |
| --- | --- | --- | --- |
| `source_product_id` | `parent_asin` | Must have for offline source records | Stable join/dedup key; cannot be used as Backend ID without explicit mapping. |
| `name` | `name` | Must have for baseline features | Main product text; blank names rejected from indexing. |
| `category_label` | `category` | Must have for category-aware MVP | Candidate grouping; **must be reviewed**, as source labels may be wrong. |
| `description` | `description` | Nice to have | Improves TF-IDF context; missing values fall back to name. |
| `brand` | `brand_candidate.name` when resolved | Nice to have | Optional signal; never replace missing brand with an invented value. |
| `specifications` | `technical_specifications.values` | Nice to have | Optional subsequent feature; values are **unverified** until approved. |
| `features` | CSV `features_json` or preserved source trace | Nice to have | Optional text signal; requires safe parsing and provenance. |
| `source_rating` / `rating_count` | CSV `average_rating`, `rating_number` | Nice to have | Research metadata only; do not interpret as site-specific purchase behavior. |
| `product_id` | Backend mapping | Must have **for production serving** | Canonical returned ID in integration. |
| `selling_price_vnd` | Backend catalog | Must have **for commerce display/filtering**, not TF-IDF | Only current approved Backend value; source Amazon price cannot be used as a selling price. |
| `availability` / `status` | Backend catalog | Must have **for commerce display/filtering**, not TF-IDF | Backend verifies actual sellability on every display response. |
| `image_url` | Backend-approved media | Required to display an image; not required by ranker | Source image URL alone is not evidence of usage rights. |

**Specification format:** `technical_specifications.values` is a versioned registry-aware dictionary. Entries may be strings (e.g. `"cpu_family": "ryzen 5"`) or numeric objects (e.g. `"physical_ram": {"value": 8, "unit": "GB"}`). Preserve units and original evidence; do not silently infer missing attributes.

### 3.2 Future user-behavior inputs (not required for content-based MVP)

If personalization is approved, possible signals are `product_view`, `add_to_cart`, `wishlist_add`, `purchase`, and `search`. Their collection is a **future Backend/Frontend contract**, not a current fact.

| Field | Requirement when event tracking exists | Remarks |
| --- | --- | --- |
| `event_id` | Must have | Supports event deduplication. |
| `event_type` | Must have | Controlled event enum. |
| `event_time` | Must have | UTC ISO-8601 timestamp. |
| `user_id` or `session_id` | At least one | Anonymous activity may use a pseudonymous session ID; avoid storing unnecessary personal data. |
| `product_id` | Must have for product events | Backend canonical identifier. |
| `variant_id` | Conditional | Only for actions against a specific variant. |
| `query` | Conditional | Search events only; redact/minimize potentially sensitive text. |

Existing authorized order/cart/wishlist records may provide these signals without creating redundant event logs. Access, consent, retention and deletion requirements must be agreed before collecting any new user behavior.

### 3.3 Proposed normalized **offline** record

This is an **AI transformation target**, not the existing Backend schema:

```json
{
  "source_product_id": "B0C2ZMJW53",
  "product_id": null,
  "name": "Acer Aspire 3 A314-23P-R3QA Slim Laptop",
  "category_label": "Laptop",
  "brand": null,
  "description": "...",
  "technical_specifications": {
    "cpu_family": "ryzen 5",
    "physical_ram": {"value": 8, "unit": "GB"},
    "installed_storage_gb": {"value": 512, "unit": "GB"}
  },
  "specification_approval": "UNVERIFIED"
}
```

The product name, source identifier and example specification value shapes come from the supplied V4.1 artifacts. `product_id: null` and `brand: null` are illustrative placeholders here and **not assertions** about the corresponding source record. The normalized record explicitly excludes an invented VND price, stock count and sellable variant.

## 4. Subset selection and data quality requirements

**Hard input gate:** Verify that the chosen V4.1 subset has **exactly 1,500 unique `parent_asin` values**, and that every selected product has **at most one** matching specification row (with missing specifications reported explicitly). Maintain an immutable `dataset_version` plus SHA-256 checksums for the subset inputs. If the 1,500 selection does not exist or this verification fails, the subset is **not yet validated**.

Quality checks to run **on the new 1,500-product selection**:

1. Total selected product/specification rows; duplicate IDs; unmatched joins; blank names.
2. Category distribution and manually reviewed category misclassification samples.
3. Nonempty descriptions, resolved brands, nonempty `technical_specifications.values`, and missingness by category.
4. `approval`, `status`, `review_issues`, conflict indicators and source provenance.
5. Potential duplicate/near-duplicate products and unresolved variant boundaries.
6. Availability of approved Backend IDs and approved public listing status before production integration.
7. Inconsistencies in numeric specification units and parsing, with questionable values excluded from any numeric comparison.

**Known risks from the uploaded 10,000-row source pool (not measured on the 1,500 subset):** unresolved category IDs, unverified specifications, unapproved VND selling prices, unverified SKU/variant boundaries and unverified media availability/rights. A concrete observed misclassification is a NETGEAR Wi-Fi range extender appearing under `Charger & Power Bank`; hence category labels are not inherently ground truth. No product may be treated as approved merely because it passed AI preprocessing.

### 4.1 Acceptance thresholds

- **For an offline experiment:** exactly 1,500 unique source IDs; no duplicate join result; all indexed items have a nonblank name; unmatched specifications and unresolved attributes are counted and disclosed, not fabricated.
- **For production:** every returned item must map to an approved Backend `product_id`; the Backend must confirm publication/sellability and current variant availability. A missing mapping or failed eligibility check excludes the item.
- Coverage/quality thresholds for brand/specifications must be selected **after** the 1,500-subset audit and agreed with stakeholders; no arbitrary coverage percentage is asserted now.

## 5. Ownership and interface requirements

| Responsibility | Owner | Proposed behavior |
| --- | --- | --- |
| Source catalog cleaning and offline experimentation | AI/Data | Join source files, validate, extract features, version index artifacts. |
| Canonical product/variant IDs, category approval and sellability | Backend | Source of truth for catalog records and commercial state. |
| Selling price, inventory, public product information and media rights | Backend | Resolve from approved catalog; never accept Amazon source prices/images as automatically publishable. |
| Similarity ranking | AI service | Return ranked canonical `product_id` values and non-probabilistic similarity scores. |
| Cart/purchase/wishlist history and user-event collection (future) | Backend/Frontend | Provide authorized access only if personalization becomes in scope. |

**Data access proposal:** Start with an approved, versioned catalog export for reproducible offline training; agree later whether refresh uses a paginated Backend API, scheduled export, or event-driven sync. AI should not assume access to the Backend database.

## 6. Backend questions requiring confirmation

1. Does Backend retain `parent_asin` (or a separate import mapping) alongside its canonical `product_id`? How will AI resolve external IDs to active products?
2. What is the authoritative definition of an approved/published product and a sellable variant? Which field/API represents it?
3. Will Backend supply an approved catalog export or read API, including category, brand, description, specifications and product-to-variant mapping?
4. Can Backend hydrate and revalidate ranked product IDs with **current** price, stock, public status and approved media before returning them to Frontend?
5. Are cart, wishlist, order and browsing events already persisted? If so, what is the supported, privacy-preserving access method for future personalization?
6. What refresh cadence and deletion/unpublication propagation are required for catalog changes?

Answers are **pending** and must not be described as implemented interfaces.

## 7. Deliverables and definition of done

**Deliverable:** This Product Metadata & User Behavior Requirements document, plus a separately generated audit report for the actual 1,500-product subset when available.

- [x] Document MVP/future use cases and source fields.
- [x] Separate source identifiers from Backend product/variant identifiers.
- [x] Define required/optional metadata and conditional behavior fields.
- [x] Define data-quality gates and ownership boundaries.
- [ ] Obtain and audit the actual selected 1,500-product files or manifest.
- [ ] Confirm Backend mapping, commercial-data contract and refresh/access method.
- [ ] Obtain AI/Backend review and approval.

**Task status recommendation:** Documentation drafted; **do not mark SWE-62 Done** until outstanding confirmations and the real 1,500-product audit are complete.
