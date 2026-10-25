# Capital One recovery feasibility

Phase 0 recommendation: **proceed with an engine focused first on 2020–2025**. The validation gate passes. This phase adds research scripts and evidence, with no engine CLI or public API.

The comparison deliverable is intentionally narrower than the retained collection: **60 US postings from 2020–2025, plus five earlier benchmark examples**. This treats 2025 as the latest completed year and keeps 2026 and current postings separate, following the working interpretation stated during collection. The user authorized up to 120 additional targeted payloads after the original 200-payload allowance was reached; 65 additional payloads were used, including one Common Crawl response.

Source acquisition ran October 8, 2026 locally, from `2026-10-09T02:02:22Z` through `03:02:59Z` UTC. Earlier archive times below describe historical captures, not the investigation's retrieval dates.

## Comparison files and sampling

Use [comparison-results.csv](../data/capital-one/comparison-results.csv) or [JSON](../data/capital-one/comparison-results.json). Each record carries its family, comparison year, exact title, identifiers, location, description, original/source URLs, source-declared dates, retrieval time, verified archive time, completeness, review status, and evidence references. [The matrix](../data/capital-one/comparison-matrix.json) links each cell to exact version keys.

| Verified capture year | Software engineering | Data/business analytics | Product management | Risk/compliance | Customer operations |
|---|---:|---:|---:|---:|---:|
| 2020 | 2 | 2 | 2 | 2 | 2 |
| 2021 | 2 | 2 | 2 | 2 | 2 |
| 2022 | 2 | 2 | 2 | 2 | 2 |
| 2023 | 2 | 2 | 2 | 2 | 2 |
| 2024 | 2 | 2 | 2 | 2 | 2 |
| 2025 | 2 | 2 | 2 | 2 | 2 |

All 60 records have verified historical capture evidence and distinct posting IDs within each cell. Thirty core records—one per cell—received source inspection and passed title, ID, qualifications, source-heading, region, capture-year, hash, and scope checks. The other 30 remain extraction candidates with `needs_review` status. The review found and corrected a department-based misclassification of an Audit UX designer and removed foreign-country and annual graduate-program records from this subset.

These are purposive examples of descriptions available in each year. Source publication dates may precede the capture year and remain separate. The families are broad: business analysts and data analysts differ, as do branch and café roles. Exact seniority, occupation, location, employment terms, and publication date should be matched before drawing substantive comparisons. The sample supports inspection of duties and qualifications; it does not measure hiring volume, skill prevalence, or a company-wide trend.

[Five 2013 benchmark records](../data/capital-one/comparison-early-benchmark.json) cover the same broad families. They are earlier recovery controls, including a university-targeted analyst posting; they are not a matched longitudinal cohort. The complete earlier recovery collection remains available as supporting evidence.

## Evidence totals and decision gate

The [offline validation report](../data/capital-one/validation.json) records:

- **6,205 Wayback candidate captures across 5,829 original URLs**, from incomplete bounded discovery. Candidates include aliases and false positives; these are not recovered-posting counts.
- **271 historical payload attempts, 265 description-bearing observations, and six failures/non-descriptions.** This includes 265 archive payloads and six recruiting copies. Repeated identical captures and the Common Crawl/Wayback duplication remain linked as evidence.
- **258 historical description versions across 242 supported posting groups:** 252 archived versions and six attributable recruiting copies. Of the archived versions, **247 have verified capture timestamps**; five have original-link encoding discrepancies and retain null archive times.
- **70 historical versions received source review.** The gate conservatively counts **69 distinct reviewed postings with verified archive evidence**, including **10 whose original URLs now return HTTP 404**. This exceeds the required 10 historical descriptions and five demonstrably unavailable originals. Current snapshots and DNS failures contribute nothing to this gate.
- **1,963 current description records across 1,958 requisitions**, retained separately. All **2,560 distinct retained response artifacts** passed SHA-256 integrity checks.

The earliest recovered, evidence-verified description is [Senior Risk Representative, captured July 1, 2013 at 15:15:40 UTC](https://web.archive.org/web/20130701151540id_/http://jobs.capitalone.com:80/chester/call-center-and-customer-service/jobid3739165-senior-risk-representative-jobs). A February 18, 2012 Taleo lead yields only a redirect document. Neither observation establishes Capital One's first posting, and earlier corporate careers indexes were not exhaustively explored after the focus shifted to recent comparisons.

## Current inventories and ownership

See [company-profile.md](company-profile.md) for verified links, ATS relationships, regions, languages, and unresolved domain leads.

| Board | Final inventory | Enumeration | Descriptions recovered |
|---|---:|---|---:|
| Global careers | 1,809 | 121 pages; reported totals reconciled | 1,809 |
| Canada | 61 | 5 pages; reported totals reconciled | 61 |
| United Kingdom | 76 | 9 pages; reported totals reconciled | 76 |
| Philippines | 5 linked role pages | Finite linked list; no reported vacancy total | 5 |
| Workday | 1,955 requisitions | 98 pages; all IDs represented in the combined collection | 12 additional detail responses |

Different boards and exact Workday paths account for duplicate source records. Three currently accessible regional requisitions were absent from the Workday inventory: `R218487`, `R246507`, and `R247919`. They are retained as a reconciliation difference, without a closure inference. This snapshot is complete for the enumerated verified boards, not a guarantee that every regional or language publication channel has been found.

## Source recovery and authenticity

Direct public HTTP retrieval precedes extraction. Raw transport bytes, response headers, method/body/header overrides, redirect evidence, hashes, and request identity are retained in [requests.jsonl](../data/capital-one/requests.jsonl). Offline processing derives descriptions from HTML, PDFs, Workday JSON, and compressed WARC records. Archived scripts are never executed.

Wayback timestamps require agreement between the final replay URL, `Memento-Datetime`, and the original URL in the replay's `Link` header. Requested and verified capture times remain separate. Five double-escaped original links fail that strict identity test even though readable text survives. Gzip replay bodies are decoded for extraction without changing retained bytes. The 2014 teller pilot's headers and actual replay timestamp were verified.

Common Crawl initially returned gateway errors for three representative collections. Adjacent indexes succeeded and the bounded probes retain 1,670 index observations, including 841 successful detail candidates. A nearby `CC-MAIN-2020-50` lookup led to a **20,290-byte WARC range retrieval**. Its HTTP 206 range, WARC target URI, original HTTP status, WARC date, index timestamp, and payload hash validate the November 28, 2020 Branch Ambassador capture. Wayback's `x-archive-src` identifies that same WARC: this proves a usable alternate retrieval route, not independent historical content or an extra version.

Attributable copies preserve three AEA December 2013 listings, USC's March 25, 2014 IT Development Program posting, and two UCF PDFs. Copies remain source-specific. Month/day precision is explicit; the PDFs' upload paths and graduation windows do not become invented publication dates. Missing original URLs and archive dates stay null.

## Failures, validation, and reproducibility

The six unsuccessful historical payloads are one redirect document, three Taleo maintenance notices, one city marketing page reached through a job-like URL, and one inaccessible archive replay returning 404. These are retained in [historical-failures.json](../data/capital-one/historical-failures.json). HTTP 200 shells and maintenance messages do not become descriptions. Timeouts, gateway errors, and legacy-domain DNS failures remain unknown availability. An original URL's observed 404 establishes that URL no longer serves the description; it does not prove when the position closed.

Development reviews cover 30 legacy positive cases, 11 additional historical positives, four negative cases, and 30 recent comparison cases, with one positive overlap. These were source inspections by Codex, not independent human or blind accuracy evaluations. No population recall estimate is justified. **All 43 regression tests pass**, exercising timestamp drift, live substitution, future publication-date conflicts, empty shells, expired notices, wrong posting identity, same-title separation, changed versions, pagination failure, rate limits, timeouts, ignored ranges, WARC locator mismatches, and budget stops. No future-publication-date conflict was found in the retained historical records.

Rebuild offline using the commands in the [README](../README.md). The [final offline audit](../data/capital-one/offline-reproducibility.json) passed: **16 canonical exports regenerated byte-for-byte**, the request manifest remained unchanged, and networking was disabled. Review expectations and WARC locators are retained beside the artifacts; the rebuilt descriptions do not depend on rendered provider output. A supplemental discovery search lacks its original query, but contributed only unused leads and does not affect result reproduction.

## Budgets and remaining work

[budget.json](../data/capital-one/budget.json) records **2,662 source observations**, a conservative **2,687-request upper bound** including provider reservations, **262,636,387 retained response bytes** (250.5 MiB), and a conservative retained-download total of 264,090,658 bytes. These remain below 3,000 requests and 1 GiB. **271 of the amended 320 historical payload allowance** were used. The initial archive-only counter omitted six recruiting copies; the final ledger and shared collector guard now include them. **25 additional Firecrawl credits were conservatively reserved**, including failed calls whose billing is unknown; no further Firecrawl spending is authorized under this budget. Acquisition and review stayed within two working days.

The focused 60-record panel is complete, so the remaining payload allowance was not spent on unrelated records. Broad historical coverage is explicitly partial: large CDX windows hit their limits, 28 of 42 broad survey probes failed, four of 17 focused index probes failed, pre-2013 coverage is uncertain, and historical regional/language coverage remains thin. Common Crawl probes cover only bounded index pages and one validated response, not complete collections. Captured originals are source artifacts, not a completeness census.

The next engine should prioritize bounded yearly discovery for 2020–2025, official archived details, and WARC retrieval where indexed payloads survive, followed by dated attributable copies. Preserve source versions and nullable dates. Before population-level comparisons, extend discovery beyond truncated indexes and define a matched title/seniority/location cohort with an independent held-out review set.

For resumption, inspect `budget.json`, `scope-amendment.json`, `comparison-matrix.json`, and discovery checkpoints first. `comparison_discovery.py` discovers only missing cells; `comparison.py --recover` stops once each cell has two eligible IDs or the amended payload cap is reached. Run acquisition scripts sequentially to maintain per-host serialization, then rebuild and verify offline. Broad historical expansion or further Firecrawl use needs a new scope/budget decision; engine implementation remains a subsequent phase.

## Clarified objective audit

The US-only ML/AI, risk, fraud, credit, business analyst, product manager, and data scientist objective supersedes the broad five-family sampling default above. See [objective-audit.md](objective-audit.md) for actual target yield, excess collection and deletion-evidence limitations, and [agent-handoff.md](agent-handoff.md) for the continuation package. Use the new compact target export for focused comparison; the original 60-record panel remains a feasibility artifact.
