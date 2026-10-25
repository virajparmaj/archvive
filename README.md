# revive-archived-jd
engine to retrieve archived job postings

See the [implementation plan](IMPLEMENTATION_PLAN.md) for the proposed first-company recovery engine and validation milestones.

Capital One Phase 0 is implemented as a bounded research collection. The primary comparison subset focuses on **2020–2025**, with current postings kept separate and a small earlier benchmark. No engine CLI or public API has been introduced.

- [Recovery feasibility and comparison scope](notes/feasibility.md)
- [Verified company sources and ownership evidence](notes/company-profile.md)
- Local, gitignored evidence and exports: `data/capital-one/`

Set up the research environment:

```sh
~/.venvs/global/bin/python -m venv .venv
.venv/bin/python -m pip install -r requirements-research-lock.txt
```

Rebuild and check the retained collection offline:

```sh
.venv/bin/python research/benchmark.py
.venv/bin/python research/review_checks.py
.venv/bin/python research/comparison_review.py
.venv/bin/python research/reprocess.py
.venv/bin/python research/verify.py
.venv/bin/python research/comparison.py
.venv/bin/python -m pytest -q
.venv/bin/python research/offline_audit.py
```

These commands require the local collection, which is deliberately excluded from Git. They parse retained HTML, PDF, Workday JSON, and WARC bytes; they do not fetch source pages. `comparison-results.csv` and `.json` are the focused comparison outputs; `comparison-early-benchmark` contains earlier controls. `current-results`, `historical-results`, and `results` retain the broader evidence separately.

Acquisition helpers are under `research/`. Run them sequentially and review checkpoints and budgets before adding requests. Successful and failed requests are cached; a timeout remains unknown. The scope amendment authorizes up to 320 historical payloads while preserving the 3,000-request, 1 GiB, and 25 additional Firecrawl-credit caps. See the feasibility report for coverage limits and resume instructions.
