"""Recover the discovered legacy sample before the broader yearly survey."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from phase0 import (
    Collector, DATA, archive_evidence, atomic_json, cdx_rows, copies, digest,
    export, extract, is_detail, now, record,
)


def import_curl(collector, name, url):
    body_path = Path(f"/private/tmp/archvive-direct-{name}.html")
    if name == "cdx":
        body_path = body_path.with_suffix(".json")
    header_path = Path(f"/private/tmp/archvive-direct-{name}.headers")
    if not body_path.exists():
        return None
    header_text = header_path.read_text()
    headers = []
    for line in header_text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            headers.append([key.lower(), value.strip()])
    key = digest(json.dumps(["GET", url, None, None], sort_keys=True).encode())
    existing = collector.requests.get(key)
    if existing:
        return existing
    item = dict(request_key=key, requested_url=url, final_url=url, method="GET",
                retrieved_at=datetime.fromtimestamp(body_path.stat().st_mtime, timezone.utc).isoformat(),
                retrieval_time_basis="local output file completion timestamp",
                transport="direct_http_curl", status=200, outcome="ok", redirects=[],
                response_headers=headers, imported_existing_probe=True)
    return collector._save(item, body_path.read_bytes())


def main():
    collector = Collector()
    original = "http://jobs.capitalone.com:80/alexandria/retail-banking/jobid6036628-full-time-teller-beacon-mall-jobs"
    replay = "https://web.archive.org/web/20141020122526id_/" + original
    item = import_curl(collector, "archive", replay)
    records = []
    outcomes = []
    if item:
        item = {**item, "original_url": original, "requested_archive_timestamp": "20141020122526"}
        records.append(record(item, extract(collector.body(item), original), historical=True))
    url = "https://web.archive.org/cdx/search/cdx?url=jobs.capitalone.com%2F%2A&output=json&filter=statuscode%3A200&filter=mimetype%3Atext%2Fhtml&filter=original%3A.*jobid.*&collapse=urlkey&limit=50&from=2013&to=2014&fl=timestamp%2Coriginal%2Cstatuscode%2Cmimetype%2Cdigest"
    index = import_curl(collector, "cdx", url)
    rows = cdx_rows(collector.body(index)) if index else []
    atomic_json(DATA / "pilot-candidates.json", rows)
    # Prefer the oldest available observations; preserve all indexed observations separately.
    candidates = sorted([row for row in rows if is_detail(row["original"])], key=lambda r: r["timestamp"])
    for i, row in enumerate(candidates[:40]):
        replay = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        item = collector.fetch(replay)
        item = {**item, "original_url": row["original"], "requested_archive_timestamp": row["timestamp"]}
        parsed = extract(collector.body(item), row["original"]) if item["outcome"] == "ok" else None
        outcome = dict(original_url=row["original"], requested_timestamp=row["timestamp"],
                       outcome=item["outcome"], request_key=item["request_key"],
                       extracted=bool(parsed), archive_capture_at=archive_evidence(item))
        if parsed:
            records.append(record(item, parsed, historical=True))
        outcomes.append(outcome)
        export(records, "pilot-results")
        atomic_json(DATA / "pilot-outcomes.json", outcomes)
        print(f"PILOT {i+1}/{min(len(candidates),40)} {outcome['outcome']} extracted={bool(parsed)} verified={bool(outcome['archive_capture_at'])}", flush=True)
    # Check original URLs independently; no DNS failure or redirect means a closed role.
    availability = []
    for original in dict.fromkeys(r["original_url"] for r in records):
        check = collector.fetch(original)
        availability.append(dict(original_url=original, status=check.get("status"), outcome=check["outcome"],
                                 observed_at=check["retrieved_at"], request_key=check["request_key"],
                                 availability="unavailable" if check.get("status") in {404,410} else
                                 "accessible" if check["outcome"] == "ok" else "unknown"))
    atomic_json(DATA / "original-availability.json", availability)
    copies(collector, [])
    print(f"PILOT done: {len(records)} extracted observations", flush=True)


if __name__ == "__main__":
    main()
