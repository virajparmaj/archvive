"""Coverage survey and payload recovery beyond the initial legacy sample."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from phase0 import (
    Collector, DATA, archive_evidence, atomic_json, cdx_rows, cdx_url, digest,
    export, extract, is_detail, now, record,
)


def index(collector, url, credit_limit=12):
    item = collector.fetch(url)
    rows = cdx_rows(collector.body(item)) if item["outcome"] == "ok" else None
    if rows is not None:
        return rows, item
    fallback_key = "firecrawl-" + digest(url.encode())
    if fallback_key in collector.requests:
        fallback = collector.requests[fallback_key]
        return cdx_rows(collector.body(fallback)) if fallback["outcome"] == "ok" else None, fallback
    # Optional accessible-page transport; no rendered replay can verify a capture.
    ledger = DATA / "firecrawl-usage.json"
    usage = json.loads(ledger.read_text()) if ledger.exists() else {"calls": [], "credits_reserved": 0}
    filename = DATA / "transport" / (digest(url.encode()) + ".json")
    filename.parent.mkdir(parents=True, exist_ok=True)
    if not filename.exists():
        if usage["credits_reserved"] >= credit_limit:
            return None, item
        usage["credits_reserved"] += 1
        attempt = dict(url=url, at=now(), reserved_credits=1)
        usage["calls"].append(attempt)
        atomic_json(ledger, usage)
        try:
            process = subprocess.run(["firecrawl", "scrape", url, "--format", "rawHtml", "--json",
                                      "-o", str(filename)], capture_output=True, timeout=60, text=True)
            attempt.update(returncode=process.returncode, stderr=process.stderr[:500])
        except subprocess.TimeoutExpired:
            attempt["error"] = "timeout"
        atomic_json(ledger, usage)
    if not filename.exists():
        return None, item
    data = json.loads(filename.read_text())
    content = data.get("rawHtml", "")
    metadata = data.get("metadata", {})
    from datetime import datetime, timezone
    fallback = dict(request_key=fallback_key, requested_url=url,
                    final_url=metadata.get("url", url), status=metadata.get("statusCode"),
                    transport="firecrawl_rendered", response_headers=[],
                    retrieved_at=datetime.fromtimestamp(filename.stat().st_mtime, timezone.utc).isoformat(),
                    outcome="ok" if metadata.get("statusCode") == 200 else "transport_failed",
                    source_metadata=metadata, provider_response_path=str(filename.relative_to(DATA)))
    fallback = collector._save(fallback, content.encode())
    return cdx_rows(content) if fallback["outcome"] == "ok" else None, fallback


def main():
    collector = Collector()
    coverage_path = DATA / "survey-coverage.json"
    coverage = json.loads(coverage_path.read_text()) if coverage_path.exists() else []
    observations_path = DATA / "survey-observations.json"
    observations = json.loads(observations_path.read_text()) if observations_path.exists() else []
    result_path = DATA / "survey-results.json"
    records = json.loads(result_path.read_text()) if result_path.exists() else []
    families = ["jobs.capitalone.com/*", "www.capitalonecareers.com/*",
                "capitalone.taleo.net/careersection/*", "cscapitalone.taleo.net/careersection/*",
                "capitalone.wd1.myworkdayjobs.com/*", "capitalone.wd12.myworkdayjobs.com/*",
                "jobs.capitalone.co.uk/*", "www.capitalonecareers.ca/*"]
    probes = [(family, "0000", "2012") for family in families]
    probes += [(family, str(year), str(year)) for year in range(2013, 2027)
               for family in ["jobs.capitalone.com/*", "www.capitalonecareers.com/job/*"]]
    probes += [(family, "2013", "2026") for family in families[2:]]
    done = {(r["family"], r["from"], r["to"]) for r in coverage}
    for family, start, end in probes:
        if (family, start, end) in done:
            continue
        rows, item = index(collector, cdx_url(family, start, end, limit=2000))
        state = dict(family=family, **{"from": start, "to": end}, request_key=item["request_key"],
                     outcome=item["outcome"] if rows is None else "index_read",
                     count=len(rows) if rows is not None else None,
                     possibly_truncated=bool(rows and len(rows) >= 2000), limit=2000)
        coverage.append(state)
        observations.extend({**row, "index_request_key": item["request_key"]} for row in rows or [])
        atomic_json(coverage_path, coverage)
        atomic_json(observations_path, observations)
        print(f"SURVEY {start}-{end} {family}: {state['outcome']} {state['count']}", flush=True)
    candidates = list({(r["original"], r["timestamp"]): r for r in observations
                       if is_detail(r["original"]) and r["statuscode"] == "200"}.values())
    # Supplemental narrower queries retain their provider envelopes and are discovery only.
    from datetime import datetime, timezone
    for filename in sorted((DATA / "transport").glob("modern-*-cdx.json")):
        data = json.loads(filename.read_text())
        metadata = data.get("metadata", {})
        rows = cdx_rows(data.get("rawHtml", "")) if metadata.get("statusCode") == 200 else None
        if rows is None:
            continue
        key = "firecrawl-extra-" + digest(metadata["sourceURL"].encode())
        item = collector.requests.get(key)
        if item is None:
            item = collector._save(dict(request_key=key, requested_url=metadata["sourceURL"],
                final_url=metadata.get("url"), status=200, transport="firecrawl_rendered",
                response_headers=[], retrieved_at=datetime.fromtimestamp(filename.stat().st_mtime, timezone.utc).isoformat(),
                outcome="ok", source_metadata=metadata, provider_response_path=str(filename.relative_to(DATA))),
                data["rawHtml"].encode())
        candidates.extend({**row, "index_request_key": key} for row in rows
                          if is_detail(row["original"]) and row["statuscode"] == "200")
    candidates = list({(r["original"], r["timestamp"]): r for r in candidates}.values())
    atomic_json(DATA / "survey-candidates.json", candidates)
    buckets = {}
    for row in candidates:
        buckets.setdefault((row["timestamp"][:4], urlsplit(row["original"]).hostname), []).append(row)
    selected = []
    existing_replays = {r["requested_url"] for r in collector.requests.values()
                        if "/web/" in r["requested_url"] and is_detail(r["requested_url"])}
    remaining = max(0, 200 - collector.historical_attempts)
    # Cached pilot captures are reprocessed offline separately, leaving room for new sources.
    for key in list(buckets):
        buckets[key] = [r for r in buckets[key]
                        if f"https://web.archive.org/web/{r['timestamp']}id_/{r['original']}" not in existing_replays]
        if not buckets[key]:
            del buckets[key]
    while buckets and len(selected) < remaining:
        for key in sorted(list(buckets)):
            if len(selected) >= remaining:
                break
            selected.append(buckets[key].pop(0))
            if not buckets[key]:
                del buckets[key]
    outcome_path = DATA / "survey-recovery-outcomes.json"
    outcomes = json.loads(outcome_path.read_text()) if outcome_path.exists() else []
    for i, row in enumerate(selected):
        if urlsplit(row["original"]).hostname not in {
                "jobs.capitalone.com", "www.capitalonecareers.com", "capitalonecareers.com",
                "capitalone.taleo.net", "cscapitalone.taleo.net", "capitalone.wd1.myworkdayjobs.com",
                "capitalone.wd12.myworkdayjobs.com", "jobs.capitalone.co.uk", "www.capitalonecareers.ca"}:
            continue
        url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        item = collector.fetch(url)
        item = {**item, "original_url": row["original"], "requested_archive_timestamp": row["timestamp"]}
        extracted = extract(collector.body(item), row["original"]) if item["outcome"] == "ok" else None
        if extracted:
            records.append(record(item, extracted, historical=True))
        outcomes.append(dict(original_url=row["original"], requested_timestamp=row["timestamp"],
                             outcome=item["outcome"], request_key=item["request_key"],
                             extracted=bool(extracted), archive_capture_at=archive_evidence(item)))
        export(records, "survey-results")
        outcomes = list({r["request_key"]: r for r in outcomes}.values())
        atomic_json(outcome_path, outcomes)
        print(f"SURVEY payload {i+1}/{len(selected)} {item['outcome']} extracted={bool(extracted)}", flush=True)
    availability = []
    for original in dict.fromkeys(r["original_url"] for r in records):
        if urlsplit(original).hostname not in {"www.capitalonecareers.com", "www.capitalonecareers.ca", "jobs.capitalone.co.uk"}:
            continue
        item = collector.fetch(original)
        parsed = extract(collector.body(item), original) if item["outcome"] == "ok" else None
        text = collector.body(item).decode("utf-8", "replace") if item["outcome"] == "ok" else ""
        explicitly_expired = bool(re.search(r"job (?:is |you are looking for is )?no longer available|job has expired|position (?:has been filled|is no longer available)", text, re.I))
        availability.append(dict(original_url=original, status=item.get("status"), outcome=item["outcome"],
                                 observed_at=item["retrieved_at"], request_key=item["request_key"],
                                 availability="unavailable" if item.get("status") in {404,410} else "accessible" if item["outcome"] == "ok" else "unknown",
                                 description_availability="unavailable" if item.get("status") in {404,410} or explicitly_expired else "accessible" if parsed else "unknown"))
    atomic_json(DATA / "modern-original-availability.json", availability)


if __name__ == "__main__":
    main()
