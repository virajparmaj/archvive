"""Offline evidence audit, inventory reconciliation, and Phase 0 gate report."""

import json
import re
from collections import Counter, defaultdict

from phase0 import DATA, atomic_json, digest, export, is_detail, source_date_conflict, historical_payload
from reprocess import apply_reviews


def read(name):
    return json.loads((DATA / f"{name}.json").read_text())


def requisition(row):
    identifiers = row["identifiers"]
    value = identifiers.get("requisition_id") or identifiers.get("structured_identifier")
    if isinstance(value, dict):
        value = value.get("value")
    return value if isinstance(value, str) and re.fullmatch(r"R\d+", value) else None


def posting_key(row, site_references):
    identifiers = row["identifiers"]
    req = requisition(row)
    if req:
        return "requisition:" + req
    site_id = identifiers.get("careers_site_job_id")
    reference = identifiers.get("reference_code") or site_references.get(site_id)
    if reference:
        return "reference:" + reference
    if site_id:
        return "career-site:" + site_id
    return "source:" + (row["original_url"] or row["source_url"])


def reconcile(records):
    boards = []
    main = read("current-inventory")
    inventories = [dict(region="Global careers", **main), *read("regional-inventories"),
                   dict(region="Philippines", **read("philippines-inventory"))]
    for inventory in inventories:
        urls = set(inventory["urls"])
        recovered = {r["source_url"] for r in records if not r["historical"]} & urls
        pages = inventory.get("pages", [])
        boards.append(dict(region=inventory["region"], enumerated=len(urls),
                           pages=len(pages) if pages else 1,
                           reported_totals=sorted({p["reported_total"] for p in pages}),
                           pagination_complete=inventory["pagination_complete"],
                           recovered=len(recovered), missing_urls=sorted(urls - recovered)))
    workday = read("workday-inventory")
    workday_ids = {p["bulletFields"][0] for p in workday["postings"]}
    current_ids = {requisition(r) for r in records if not r["historical"]}
    return dict(boards=boards, workday=dict(reported=workday["reported_total"],
                pages=len(workday["pages"]), unique_requisitions=len(workday_ids),
                pagination_complete=workday["pagination_complete"],
                uncovered_requisitions=sorted(workday_ids - current_ids),
                additional_description_records=len(read("workday-results")),
                regional_ids_absent_from_workday=sorted(current_ids - workday_ids)))


def main():
    observations = [json.loads(line) for line in (DATA / "requests.jsonl").read_text().splitlines()]
    requests = {r["request_key"]: r for r in observations}
    checked = set()
    for item in observations:
        if item.get("artifact_path") and item["artifact_path"] not in checked:
            assert digest((DATA / item["artifact_path"]).read_bytes()) == item["sha256"]
            checked.add(item["artifact_path"])
    records = apply_reviews(read("results"))
    site_references = {r["identifiers"].get("careers_site_job_id"): r["identifiers"]["reference_code"]
                       for r in records if r["identifiers"].get("careers_site_job_id")
                       and r["identifiers"].get("reference_code")}
    postings = defaultdict(list)
    for row in records:
        assert digest(row["description"].encode()) == row["content_hash"]
        for evidence in row["evidence"]:
            assert evidence["request_key"] in requests
            assert requests[evidence["request_key"]]["sha256"] == evidence["source_sha256"]
        row["posting_key"] = posting_key(row, site_references)
        postings[row["posting_key"]].append(row)
    records = export(records)
    export([r for r in records if r["historical"]], "historical-results")
    export([r for r in records if not r["historical"]], "current-results")
    atomic_json(DATA / "postings.json", [dict(posting_key=key,
                version_keys=[r["version_key"] for r in rows],
                original_urls=sorted({r["original_url"] for r in rows if r["original_url"]}),
                source_urls=sorted({r["source_url"] for r in rows})) for key, rows in sorted(postings.items())])
    historical = [r for r in records if r["historical"]]
    verified = [r for r in historical if r["archive_timestamp_verified"]]
    reviewed = [r for r in verified if r["review_status"] == "validated"]
    unavailable = {r["original_url"]: r for r in read("modern-original-availability")
                   if r["description_availability"] == "unavailable"}
    gate_missing = [r for r in reviewed if r["original_url"] in unavailable]
    captures = [i for i in observations if historical_payload(i["requested_url"])]
    extracted_keys = {(e["request_key"],e["source_sha256"]) for r in historical for e in r["evidence"]}
    candidates = read("survey-candidates")
    comparison_observations = read("comparison-discovery")
    comparison_candidates = [r for o in comparison_observations for r in o["candidates"]]
    wayback_candidates = list({(r["original"],r["timestamp"]):r for r in candidates+comparison_candidates}.values())
    cc_observations = read("commoncrawl-probes") + read("commoncrawl-targeted-probes")
    cc_candidates = [r for o in cc_observations for r in o["index_records"]
                     if r.get("status")=="200" and is_detail(r["url"])]
    provider_credits = read("firecrawl-usage")["credits_reserved"]+6
    provider_bytes = sum(p.stat().st_size for p in (DATA/"transport").glob("*.json"))
    budget = dict(source_observations=len(observations),
                  conservative_request_upper_bound=len(observations)+provider_credits+sum(len(r.get("redirects",[])) for r in observations),
                  source_request_limit=3000,retained_response_bytes=sum(r.get("bytes",0) for r in observations),
                  conservative_retained_download_bytes=sum(r.get("bytes",0) for r in observations)+provider_bytes,
                  byte_limit=1024**3,historical_payloads=len(captures),historical_payload_limit=320,
                  historical_archive_payloads=sum("/web/" in i["requested_url"] or "data.commoncrawl.org/" in i["requested_url"] for i in captures),
                  historical_copy_payloads=sum("/web/" not in i["requested_url"] and "data.commoncrawl.org/" not in i["requested_url"] for i in captures),
                  additional_firecrawl_credits_reserved=provider_credits,additional_firecrawl_credit_limit=25)
    assert budget["conservative_request_upper_bound"]<=3000
    assert budget["conservative_retained_download_bytes"]<=1024**3
    assert len(captures)<=320 and provider_credits<=25
    atomic_json(DATA/"budget.json",budget)
    atomic_json(DATA/"discovery-summary.json",dict(
        wayback_candidate_captures=len(wayback_candidates),wayback_original_urls=len({r["original"] for r in wayback_candidates}),
        comparison_index_probes=len(comparison_observations),comparison_index_outcomes=dict(Counter(o["outcome"] for o in comparison_observations)),
        commoncrawl_index_observations=sum(len(o["index_records"]) for o in cc_observations),
        commoncrawl_successful_detail_candidates=len(cc_candidates),
        limitations="Bounded, incomplete indexes; candidates may include false positives, aliases and repeated versions. Counts are not company hiring volume."))
    atomic_json(DATA/"supplemental-discovery-manifest.json",[dict(
        path=str(p.relative_to(DATA)),sha256=digest(p.read_bytes()),
        source_metadata=json.loads(p.read_text()).get("metadata"),
        role="discovery only; not archive capture authentication") for p in sorted((DATA/"transport").glob("*.json"))])
    earliest = min(verified, key=lambda r:r["archive_capture_at"])
    summary = dict(
        source_observations=len(observations), unique_request_keys=len(requests),
        request_outcomes=dict(Counter(r["outcome"] for r in observations)),
        retained_response_bytes=sum(r.get("bytes", 0) for r in observations),
        artifacts_integrity_verified=len(checked),
        retrieval_window=dict(first=min(r["retrieved_at"] for r in observations), last=max(r["retrieved_at"] for r in observations)),
        historical_candidates=dict(captures=len(wayback_candidates), unique_urls=len({r["original"] for r in wayback_candidates})),
        historical_payloads=dict(attempted=len(captures), extracted=sum((i["request_key"],i.get("sha256")) in extracted_keys for i in captures),
                                 failures=sum((i["request_key"],i.get("sha256")) not in extracted_keys for i in captures)),
        description_versions=len(records), historical_versions=len(historical),
        archive_versions=len([r for r in historical if r["source_type"] == "archive_official"]),
        verified_archive_versions=len(verified), attributable_copy_versions=len([r for r in historical if r["source_type"] == "attributable_copy"]),
        distinct_historical_postings=len({r["posting_key"] for r in historical}),
        historical_versions_by_capture_year=dict(Counter(r["archive_capture_at"][:4] if r["archive_capture_at"] else "unverified" for r in historical)),
        current_description_records=len(records)-len(historical),
        distinct_current_requisitions=len({requisition(r) for r in records if not r["historical"]}),
        postings_with_multiple_versions=sum(len(rows)>1 for rows in postings.values()),
        manually_validated_historical_versions=sum(r["review_status"] == "validated" for r in historical),
        future_publication_date_conflicts=[r["version_key"] for r in historical if source_date_conflict(r)],
        earliest_verified_description={k:earliest[k] for k in ["title","original_url","source_url","archive_capture_at","request_key"]},
        current=reconcile(records), gate=dict(
            verified_reviewed_distinct_postings=len({r["posting_key"] for r in reviewed}),
            reviewed_distinct_postings_with_unavailable_original=len({r["posting_key"] for r in gate_missing}),
            passed=len({r["posting_key"] for r in reviewed})>=10 and len({r["posting_key"] for r in gate_missing})>=5,
            examples=[dict(title=r["title"], archive_request_key=r["request_key"],
                           live_request_key=unavailable[r["original_url"]]["request_key"],
                           original_url=r["original_url"], status=unavailable[r["original_url"]]["status"])
                      for r in gate_missing]))
    atomic_json(DATA / "validation.json", summary)
    atomic_json(DATA / "historical-failures.json", [dict(request_key=i["request_key"], source_url=i["requested_url"],
                outcome=i["outcome"], artifact_path=i.get("artifact_path"),
                extraction_outcome="no_supported_description") for i in captures if (i["request_key"],i.get("sha256")) not in extracted_keys])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
