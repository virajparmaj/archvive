# Capital One focused recovery handoff

## Objective and boundaries

Recover US-only Capital One descriptions captured during 2020–2025, focused on ML/AI, risk, fraud, credit, business analysts, product managers, and data scientists. Exclude Canada, Philippines, UK, India, and every other non-US location. Unknown/conflicting locations stay in a review queue. Current and earlier benchmark material is supporting evidence only. No engine CLI/API, full global recrawl, new broad software/branch sample, or additional paid discovery is needed.

Read `notes/objective-audit.md` before `notes/feasibility.md`; the earlier five-family quota is superseded. No agent has been dispatched by creating this package.

## Inputs and evidence

- `data/capital-one/target-comparison-compact.json`: 31 candidate versions / 29 posting groups; default comparison input. Titles can overlap tags; do not count tag totals as distinct jobs.
- `objective-audit.json`: reproducible counts and limitations.
- `target-comparison-removals.json`: reversible cleaning evidence, loaded only when needed.
- `target-location-review.json`: seven non-US/uncertain-location title matches; inspect source evidence, never infer US from corporate boilerplate.
- `historical-results.json`: full source-specific descriptions and provenance; join on version_key.
- `requests.jsonl`, `artifacts/`: original response bytes, headers, redirects, hashes. Data is gitignored: transfer the entire data/capital-one directory through the approved workspace/artifact mechanism, not merely a Git checkout. Pin its manifest hash for any transfer.
- `comparison-discovery.json`, survey files, Common Crawl index observations: cached leads; reuse before network discovery.

## Next actions in order

1. Verify title/duties/location for the 31 candidates; 11 already have validated source review. Check the five original-404 observations and retain their observation dates. Twenty-six versions lack exact original-availability evidence; deduplicate URLs before checking. DNS failures/timeouts remain unknown.
2. Review questionable source location strings and classify generic titles only from occupation-specific duties. Audit/compliance alone is not automatically a requested risk/fraud role; legal/design AI domain mentions are excluded.
3. Prioritize missing fraud and ML engineering, then credit and data science, using cached 2020–2025 candidate indexes. Do not fill an arbitrary two-per-year quota with unrelated jobs. Select comparable duties/seniority and distinguish source posting dates from capture dates.
4. If deletion during 2020–2025 is required literally, find a historical last-live / first-unavailable interval from authenticated captures/status evidence. A 2026 404 alone cannot satisfy it. Report interval precision and surviving aliases; closure and deletion are not interchangeable.
5. Manually validate recovered text, identity, capture authenticity, and distinct versions. Keep same-title requisitions separate. Avoid treating Common Crawl and Wayback copies of the same upstream capture as independent content.
6. Deliver compact role-based comparison inputs, gap tables and resumable checkpoints. Draw no hiring-volume or prevalence conclusions from this purposive sample. Keep a small relevant earlier benchmark separate.

## Budget and reproduction

Maximum remaining at audit: 313 conservative source requests, 49 historical payloads, 809,651,166 bytes, zero additional Firecrawl credit reservations. Recalculate from the shared manifest/budget before any network run. Public HTTP first, one request per host, cached acquisition through Collector; no untracked ad hoc requests. Stop with a documented checkpoint when caps are reached.

Use the existing project `.venv` and pinned research requirements. Reproduce this focused audit with `.venv/bin/python research/objective_audit.py`; run `.venv/bin/python -m pytest -q` for relevant existing checks. The original full offline audit is `.venv/bin/python research/offline_audit.py` and should remain intact. Inspect cleaning removals and preserved qualifications before interpreting comparison text. Do not replace canonical evidence with cleaned text.

Completion means a transparent US/occupation/year coverage table, reviewed recoveries with dated original-availability evidence, separately stated deletion-time certainty, and documented remaining gaps. Passing the old feasibility gate alone is insufficient.
