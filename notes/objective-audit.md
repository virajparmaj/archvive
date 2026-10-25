# Audit against the clarified objective

The feasibility gate passed, but the user's target research is **partial**. The clarified scope is US jobs only, archived during 2020–2025 and no longer available at their original URLs, focused on ML/AI, risk, fraud, credit, business analyst, product management, and data scientist roles. Proof that deletion itself happened during that window is a separate, currently unmet requirement.

This audit supersedes the earlier five-family comparison default. That default was our sampling choice, not the user's requested occupation coverage.

## What actually matches

A conservative offline title and positive-US-evidence filter finds **31 description versions across 29 posting groups**. Of these, **11 versions already have validated source reviews**, and **five have exact-original-URL HTTP 404 observations from October 9, 2026 UTC**. These checks do not establish deletion dates or exclude surviving aliases. The other 26 versions need original-availability evidence. No posting has a proven deletion date within 2020–2025.

| Archive capture year | Target description versions |
|---|---:|
| 2020 | 5 |
| 2021 | 6 |
| 2022 | 5 |
| 2023 | 3 |
| 2024 | 5 |
| 2025 | 7 |

Overlapping title tags: product management 15, business analyst 6, risk 6, data scientist/data science 4, ML/AI 1, credit 1, fraud 0. The ML match is a product manager for Machine Learning Experience, not a recovered ML engineer. Credit overlaps a data scientist role. Fraud and dedicated ML engineering coverage remain gaps. These are matches in the recovered corpus, not estimates of available archive coverage.

The classifier excludes lawyers/designers merely mentioning AI/risk in their departments. It does not elevate generic data analysts or software engineers into requested professions. Title filtering can miss relevant duties hidden behind generic titles: those require later source review, not inflated counts. Seniority and graduate titles are not automatically excluded. Seven title-matched records have non-US or insufficient location evidence and remain outside the target export; their locations need inspection, particularly conflicting legacy location strings. A non-US job cannot enter because US law appears in its legal footer.

## What was extra

The retained collection contains 258 historical versions. Only 107 have verified captures during 2020–2025; 97 of those meet the existing conservative US-evidence filter. Of the earlier 60-record comparison panel, only **26** match this narrower occupation filter. Therefore **34 panel records are outside the clarified target**, although they remain useful recovery controls. The separate 1,963 current source records, foreign postings, earlier examples, and 2026 captures are supporting research, not target results. Retain a small earlier benchmark, not the entire old corpus in comparison prompts.

The original plan authorized current/global inventory and early-history feasibility exploration. That work was within the original plan but is excessive for the now clarified analytical objective. Archive feasibility success must not be reported as completion of this narrower research.

## Efficiency and compact comparisons

Retrieval is reproducible and cached, with preserved raw bytes, hashes, headers, per-host pacing, and offline extraction. Scope efficiency was weaker: full current/regional collection and generic role sampling consumed effort outside the eventual target. Future work should reuse discovery indexes, classify candidate titles and locations before fetching, and spend only on explicit missing occupation/year evidence.

The offline audit made **zero source requests**. Recorded usage remains 2,687 conservative requests of 3,000; 271 historical payloads of 320; 264,090,658 conservative bytes of 1 GiB; all 25 additional Firecrawl credits reserved. Remaining allowance: **313 requests, 49 historical payloads, 809,651,166 bytes, zero additional Firecrawl credit reservations**. These are ceilings, not spending targets.

`target-comparison-compact.json` is the new agent input. It contains identity, location, dates, review state, availability evidence, role tags, and comparison text. Raw HTML, repeated source URLs, full evidence envelopes, and boilerplate do not travel in each prompt. Exact evidence remains linked by version key to `historical-results.json`.

Conservative cleaning removes title/location duplicates, standalone navigation/URLs, an explicitly recognized company introduction, and the standard legal/recruiting footer. Role-specific context and all duties/qualifications before that footer remain. Every removed line and reason is recorded in `target-comparison-removals.json`. The full descriptions remain untouched. Description text falls from **190,806 to 136,049 characters (28.7%)**; this is character reduction, not a tokenizer measurement. Other varied introductions remain until explicitly reviewed as generic: deleting every introductory paragraph would risk removing team-specific evidence.

Run `.venv/bin/python research/objective_audit.py` offline to reproduce the four new JSON outputs. This does not alter the original canonical exports or their offline reproducibility baseline. The focused extraction still needs source review; it does not justify population-level trends or a balanced occupational comparison.
