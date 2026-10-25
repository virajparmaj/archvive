"""Export the retained historical collection for Degent, entirely offline."""

import gzip
import hashlib
import io
import json
import re
import shutil
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from warcio.archiveiterator import ArchiveIterator

from phase0 import DATA, extract, json_postings, soup
from reprocess import native_record


ROOT = DATA.parent / "historical-postings-handover"
KEYS = [
    "source_record_id", "company", "title", "url", "url_aliases", "requisition_id",
    "provider", "provider_posting_id", "published_at", "published_at_raw",
    "published_at_provenance", "updated_at", "updated_at_raw", "updated_at_provenance",
    "captured_at", "captured_at_provenance", "wording_valid_at",
    "wording_valid_at_provenance", "locations", "employment_type", "description",
    "description_completeness", "evidence_files", "notes",
]


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iso_date(raw):
    """Normalize only explicit calendar components; never infer a missing component."""
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}(?:-\d{2})?", raw):
        return raw
    if re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return raw
        except ValueError:
            return None
    return None


def retain_body(raw, request):
    """Copy original bytes and supply an explicitly derived decoded HTML when needed."""
    digest = sha256(raw)
    is_warc = "data.commoncrawl.org/" in request["requested_url"]
    compressed = raw.startswith(b"\x1f\x8b")
    extension = ".warc.gz" if is_warc else ".pdf" if raw.startswith(b"%PDF") else (
        ".html.gz" if compressed else ".html"
    )
    original = f"evidence/original/{digest}{extension}"
    (ROOT / original).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / original).write_bytes(raw)
    files = [original]
    payload = raw
    if is_warc:
        responses = [r for r in ArchiveIterator(io.BytesIO(raw)) if r.rec_type == "response"]
        # This export contains one response per retained range-request WARC member.
        assert len(responses) == 1
        # Reiterate: ArchiveIterator streams must be read before advancing the iterator.
        for member in ArchiveIterator(io.BytesIO(raw)):
            if member.rec_type == "response":
                payload = member.content_stream().read()
    elif compressed:
        payload = gzip.decompress(raw)
    if is_warc or compressed:
        decoded = f"evidence/decoded/{digest}.html"
        (ROOT / decoded).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / decoded).write_bytes(payload)
        files.append(decoded)
    return files, payload


def source_entry(payload, parsed):
    if parsed["extraction_kind"] not in {"jobposting_jsonld", "commoncrawl_warc"}:
        return None
    for script in soup(payload).select('script[type="application/ld+json"]'):
        try:
            entries = json_postings(json.loads(script.get_text()))
            for entry in entries:
                if entry.get("description") == parsed.get("description_html"):
                    return entry
        except (ValueError, TypeError):
            continue
    return None


def source_metadata(parsed, entry):
    locations = parsed.get("location")
    locations = locations if isinstance(locations, list) else [locations] if locations else []
    employment = entry.get("employmentType") if entry else None
    known_types = {
        "full-time", "full time", "full_time", "part-time", "part time", "part_time",
        "contract", "contractor", "temporary", "intern", "internship", "per diem",
        "per_diem", "volunteer", "other", "permanent", "fixed-term", "fixed term",
    }
    if not isinstance(employment, str) or employment.lower().strip() not in known_types:
        employment = None
    text = parsed["description"]
    if not locations and parsed["extraction_kind"] == "university_pdf":
        primary = re.search(r"Primary Location:\s*([^\n]+)", text)
        others = re.search(r"Other Locations:\s*([^\n]+)", text)
        if primary:
            locations.append(primary[1].strip())
        if others:
            locations.extend(v.strip() for v in others[1].split(",") if v.strip())
    if employment is None:
        schedule = re.search(
            r"(?:^|\n)(?:Schedule|Employment Type)(?:[ \t]*:[ \t]*|[ \t]*\n[ \t]*)([^\n]+)",
            text,
        )
        if schedule and schedule[1].strip().lower() in known_types:
            employment = schedule[1].strip()
    return locations, employment


def completeness(canonical, observation, parsed):
    if parsed["extraction_kind"] == "university_pdf":
        return "complete", "All retained PDF pages are included in the preserved text."
    review = canonical.get("review_evidence") or {}
    checks = review.get("checks", {})
    reviewed_boundaries = checks.get("source_sections") or (
        "boundaries" in review.get("review_method", "") and checks.get("no_related_jobs")
    )
    if (canonical["completeness"] == "full" and review.get("passed") and reviewed_boundaries
            and review.get("request_key") == observation["request_key"]):
        return "complete", "Existing passed source review includes description section boundaries."
    if parsed["extraction_kind"] == "aea_recruiting_copy":
        return "partial", "Saved extraction ends before Application Instructions; full page is included."
    return "unknown", (
        "No conclusive completeness review for this observation. The collector's section-presence "
        "heuristic alone does not establish completeness or truncation."
    )


def make_record(canonical, observation, request, parsed, files, entry, groups, subset):
    key = canonical["version_key"]
    request_key = observation["request_key"]
    pointer = f"evidence/collection/requests.jsonl, request_key={request_key}"
    canonical_pointer = f"evidence/collection/historical-results.json, version_key={key}"
    result = dict.fromkeys(KEYS)
    dates = parsed.get("source_declared_dates", {})
    ids = parsed.get("identifiers", {})
    locations, employment = source_metadata(parsed, entry)
    quality, quality_reason = completeness(canonical, observation, parsed)
    aliases = groups[canonical["posting_key"]]["original_urls"]
    result.update(
        source_record_id=f"archvive:{key}:{request_key}", company=canonical["company"],
        title=parsed.get("title"), url=canonical["original_url"],
        url_aliases=[u for u in aliases if u and u != canonical["original_url"]],
        requisition_id=ids.get("requisition_id") or ids.get("reference_code"),
        locations=locations, employment_type=employment, description=canonical["description"],
        description_completeness=quality, evidence_files=files + [
            "evidence/collection/historical-results.json", "evidence/collection/requests.jsonl",
            "evidence/collection/postings.json",
        ],
        notes=[
            f"comparison_subset={'true' if key in subset else 'false'}",
            "Only comparison_subset=true records enter the focused US/occupation comparisons.",
            f"Canonical version_key={key}; posting_key={canonical['posting_key']}; "
            f"request_key={request_key}; source_type={observation['source_type']}.",
            f"Description source: {canonical_pointer}, description. Verified identical to offline "
            f"source extraction at {parsed['extraction_selector']}. No comparison cleaning applied.",
            f"Source URL: {observation['source_url']}",
            f"Source identifiers (unmodified): {json.dumps(ids, ensure_ascii=False)}",
            f"Completeness: {quality_reason}",
            "provider/provider_posting_id are null: ATS/board provider mapping has not been verified. "
            "Native board and copy IDs remain in the source identifiers note.",
        ],
    )
    for prefix, field in [("published_at", "datePosted"), ("updated_at", "dateModified")]:
        raw = dates.get(field)
        result[prefix] = iso_date(raw)
        result[prefix + "_raw"] = raw
        if raw is not None:
            result[prefix + "_provenance"] = (
                f"{files[-1]}: matching JobPosting.{field}; raw={json.dumps(raw)}. "
                f"Offline extraction source_declared_dates.{field}; {pointer}."
            )
    result["captured_at"] = observation.get("retrieved_at")
    if result["captured_at"]:
        result["captured_at_provenance"] = (
            f"{pointer}, retrieved_at; basis={observation.get('retrieval_time_basis') or request.get('retrieval_time_basis') or 'UTC time after HTTP response body read'}. "
            "This is Archvive's retrieval time, not publication or historical archive time."
        )
    archive = observation.get("archive_capture_at")
    if observation.get("archive_timestamp_verified") and archive:
        result["wording_valid_at"] = archive
        warc = observation.get("warc_evidence")
        if warc:
            result["wording_valid_at_provenance"] = (
                f"{files[0]}: WARC-Date={warc['warc_date']}, WARC-Target-URI={warc['target_uri']}; "
                f"record_id={warc['record_id']}; verified against retained index locator in "
                f"{canonical_pointer}, evidence[].warc_evidence."
            )
        else:
            headers = dict(request["response_headers"])
            result["wording_valid_at_provenance"] = (
                f"{pointer}: response_headers memento-datetime={headers.get('memento-datetime')!r}, "
                f"link rel=original; final_url={request.get('final_url')!r}. "
                "Memento timestamp, final replay timestamp, and original URI identity agree. "
                f"Evidence body: {files[0]}."
            )
    elif observation["source_type"] == "attributable_copy":
        result["wording_valid_at"] = result["captured_at"]
        result["wording_valid_at_provenance"] = (
            f"{pointer}, retrieved_at, with retained response body {files[0]}. "
            "Establishes wording of the recruiting copy at retrieval only; old issue/publication "
            "labels and URL paths do not prove historical wording."
        )
    else:
        result["notes"].append(
            "Historical archive timestamp failed the collector's authenticity/URI checks; "
            "wording_valid_at is null. Requested timestamps are retained in source metadata only."
        )
    if ids.get("reference_code") and not ids.get("requisition_id"):
        result["notes"].append(
            "requisition_id comes from source identifiers.reference_code (Reference Code, explicit "
            "Taleo job parameter, or PDF's native job identifier); it is not the career-board page ID."
        )
    if entry and entry.get("employmentType") is not None:
        result["notes"].append(
            f"Source JobPosting.employmentType raw={json.dumps(entry['employmentType'])}. "
            "Unrecognized codes are not interpreted as employment types; source values remain "
            "in the original HTML. Only explicit recognized types populate employment_type."
        )
    for field, raw in dates.items():
        if field not in {"datePosted", "dateModified"}:
            result["notes"].append(
                f"Separate source date: {field}={json.dumps(raw)}; retained at {canonical_pointer}, "
                f"source_declared_dates.{field}. A copy/issue date is not an original posting date."
            )
    if result["published_at"] and archive and result["published_at"][:10] > archive[:10]:
        result["notes"].append(
            "Source-declared publication date is after the verified archive capture; both facts "
            "are retained. Do not use the publication label to date this captured wording."
        )
    if len(canonical["evidence"]) > 1:
        result["notes"].append(
            "Canonical version has multiple saved observations; each observation is a separate "
            "export record, including identical text and the same upstream capture via two routes."
        )
    return result


def statistics(records, mappings):
    fields = ["published_at", "updated_at", "captured_at", "wording_valid_at"]
    return {
        "record_count": len(records),
        "canonical_version_count": len({m["version_key"] for m in mappings}),
        "comparison_subset_record_count": sum(m["comparison_subset"] for m in mappings),
        "comparison_subset_version_count": len({m["version_key"] for m in mappings if m["comparison_subset"]}),
        "company_distribution": dict(Counter(r["company"] for r in records)),
        "year_distributions": {
            field: dict(sorted(Counter(r[field][:4] if r[field] else "unknown" for r in records).items()))
            for field in fields
        },
        "verified_archive_capture_year_distribution": dict(sorted(Counter(
            m["verified_archive_capture_at"][:4] if m["verified_archive_capture_at"] else "unknown"
            for m in mappings
        ).items())),
        "company_by_verified_archive_capture_year": {"Capital One": dict(sorted(Counter(
            m["verified_archive_capture_at"][:4] if m["verified_archive_capture_at"] else "unknown"
            for m in mappings
        ).items()))},
        "missing_dates": {field: sum(r[field] is None for r in records) for field in fields},
        "records_without_verified_historical_wording_date": sum(
            m["verified_archive_capture_at"] is None for m in mappings
        ),
        "records_without_original_evidence": sum(not m["original_evidence_files"] for m in mappings),
        "records_with_empty_description": sum(not r["description"] for r in records),
        "description_completeness": dict(Counter(r["description_completeness"] for r in records)),
    }


def readme(stats):
    archive = stats["verified_archive_capture_year_distribution"]
    publication = stats["year_distributions"]["published_at"]
    years = sorted(set(archive) | set(publication))
    table = "\n".join(f"| {y} | {archive.get(y, 0)} | {publication.get(y, 0)} |" for y in years)
    return f"""# Historical job-posting handover to Degent

Generated from the saved local Archvive collection on October 8, 2026 (America/Chicago).
Export timestamp (UTC) is recorded separately in manifest.json. No source page was fetched
during this export. Existing retrieval logs are dated October 9 UTC / October 8 Chicago.

## Scope and record counts

All **{stats['canonical_version_count']} canonical historical description versions** are included.
They expand to **{stats['record_count']} JSONL records**, one per retained observation: six versions
have two separately saved archive captures and one version has both Wayback and Common Crawl
retrievals of the same upstream capture. All are retained; no duplicates were removed.
The 1,963 live/current canonical records are outside this historical export.

The **31 focused US/occupation canonical versions** are explicitly flagged using the exact
notes string `comparison_subset=true`; all other records have `comparison_subset=false`.
The same flag is a boolean in manifest.json's record mappings, alongside version_key,
request_key and posting_key. There are **{stats['comparison_subset_record_count']} flagged JSONL records**.
Only flagged records enter the focused comparison. The flag reproduces membership in the
existing target-comparison-compact.json; it is a candidate scope selection, not a new
occupation classification or proof that each record passed manual review. Its cleaned
comparison_text is never used as a description in this export. Original subset selection
metadata and its generating audit are included under evidence/collection/ and
evidence/extraction-code/ for reproducibility. Tags are not newly extracted.

## Files and collection method

- historical-postings.jsonl: UTF-8, exactly the requested keys, one JSON object per line.
- evidence/original/: byte-for-byte saved HTML, PDF, gzip HTML and compressed WARC members.
  Hash filenames identify actual bytes, independent of record identity.
- evidence/decoded/: losslessly decompressed HTML or extracted WARC HTTP payloads, provided
  for convenience. These are derived representations; the original compressed bytes remain.
- evidence/collection/historical-results.json: original canonical export, copied unchanged.
- evidence/collection/requests.jsonl: relevant exact original request-log lines, copied
  without reserialization, including the Common Crawl index request supporting its locator.
- evidence/collection/postings.json: original saved ID/alias grouping, copied unchanged.
- evidence/collection/target-comparison-compact.json: original 31-version selection.
- evidence/extraction-code/: original collector/parser, reprocessor, WARC decoder, scope
  audit and pinned requirements, copied unchanged. They document historical collection
  and extraction, including selectors and prior review checks.
- manifest.json: per-record mappings, original evidence hashes, comparison flags,
  source-file hashes, and package file hashes. validation.json: counts and check results.
- validate.py: standalone offline validation with Python 3; run `python3 validate.py`.

Original acquisition used public HTTP, verified Wayback replay responses, a bounded
Common Crawl WARC range request, and attributable university/AEA recruiting copies.
The export verifies original SHA-256 hashes and re-extracts every saved observation with
the existing parser. Every exported description must exactly equal both the canonical
description and its offline source extraction. HTML tags/entities become text with
section/list boundaries; PDF text comes from all retained pages in reading order.
No model rewriting, skill extraction, requirement-strength assignments, comparison
cleaning, new deduplication, or inferred missing paragraphs is applied. All preserved
company introductions, duties, qualifications, pay, benefits and headings remain.

Stable IDs are `archvive:<existing version_key>:<existing request_key>`. The existing
version_key is based on original URI, language and description hash; request_key
distinguishes saved observations. Distinct titles, requisitions, URLs and captures are
not merged by this export. Original evidence files may be shared by records without
merging the records. Alias lists reproduce existing supported ID groups, never title
similarity; live aliases can be listed without adding their live descriptions.

## Date meanings and provenance

- published_at: normalized explicit JobPosting.datePosted only. Original spelling is
  in published_at_raw and the precise source field/file is named in provenance.
  Non-padded calendar dates are zero-padded without adding precision. Copy publication,
  AEA issue labels, PDF URL directories, validThrough and HTTP Last-Modified are not
  original posting dates; they remain in source evidence/notes where available.
- updated_at: explicit JobPosting.dateModified only, with the same raw/provenance rule.
  HTTP Last-Modified is not silently converted into a job update date.
- captured_at: Archvive's local retrieval timestamp from requests.jsonl, using the
  logged time basis. This dates the saved acquisition, not the original wording.
- wording_valid_at: verified historical capture time when Memento headers, replay URL
  timestamp and original URI identity agree, or verified WARC-Date/target/locator.
  For the six live attributable recruiting copies, this is the modern retrieval time
  only. An old publication label on those pages does not establish historical wording.
  Five archive responses failing the collector's authenticity/URI checks have null
  wording_valid_at. Requested archive timestamps remain in the evidence, not as facts.

Dates are never filled from a different kind of date. Null provenance accompanies a
missing date. Archive dates are point observations, not proof of continuous unchanged
wording, posting closure or deletion. Deletion during 2020–2025 is not established.
Source-declared dates that postdate a capture are retained and flagged in record notes.

## Distribution and missing data

All **{stats['record_count']} records are Capital One**. Counts below are exported observation
records, not unique jobs or hiring volume. “unknown” includes unverified archive dates
and attributable copies that have no verified historical capture.

| Year | Verified archive capture | Source publication |
|---|---:|---:|
{table}

Missing dates: published_at **{stats['missing_dates']['published_at']}**; updated_at
**{stats['missing_dates']['updated_at']}**; captured_at **{stats['missing_dates']['captured_at']}**;
wording_valid_at **{stats['missing_dates']['wording_valid_at']}**.
Records lacking a verified historical wording date: **{stats['records_without_verified_historical_wording_date']}**
(the six modern copies plus five unverified archive responses).
Records missing original evidence: **{stats['records_without_original_evidence']}**.
Empty descriptions: **{stats['records_with_empty_description']}**.
Completeness counts: {json.dumps(stats['description_completeness'], sort_keys=True)}.
All source fields' year distributions are also in validation.json.

## Completeness and known limitations

“complete” means all retained PDF pages or an existing passed source review that
explicitly inspected description boundaries for this observation. It describes the
saved source, not a guarantee of what the employer originally published elsewhere.
“partial” applies to the three AEA text extractions, which end before Application
Instructions; the entire original HTML is retained for recovery. “unknown” means no
conclusive completeness assessment. The prior collector's automatic “full/partial”
section-presence heuristic is preserved in canonical evidence but not treated as
conclusive completeness here. Missing text is never reconstructed.

The preserved body is the existing description extraction, not all site chrome.
Legacy parsers excluded forms/scripts/styles/sharing/apply controls, and HTML text
normalization removed script/style/navigation nodes and blank lines. JSON-LD descriptions
can differ from visible employer pages. All original response bytes are supplied so
Degent can examine any omitted surrounding page content. PDF layout, bullets and text
reading order may differ from visual rendering; the original PDFs remain authoritative.

The sample is purposive and incomplete across years, geographies and occupations.
The full export includes foreign locations, earlier benchmarks and 2026 captures;
use the explicit comparison flag to restrict focused analyses. Some legacy location
strings are ambiguous or conflicting; structured location values and saved strings
are retained without geocoding or inferring a country from employer boilerplate.
Employment types are only explicit recognized source employmentType/Schedule values.
Some source employmentType fields contain occupation codes (for example DX) rather
than employment types; these remain in raw-source notes and are not interpreted. Provider
mapping is unverified and left null; native IDs remain in notes. Reference Code,
explicit Taleo job parameters and native PDF job IDs can supply requisition_id, while
career-board page IDs are not substituted for a requisition.

Wayback and Common Crawl can expose the same upstream capture; the Branch Ambassador
record has exactly that relationship. It remains two observations, not independent
corroboration. The collection cannot establish hiring prevalence, deletion dates or
that an original URL has no surviving alias. Existing review status is in manifest.json.

## Validation

Every JSONL line parses, every requested key is present, record IDs are unique, all
date values preserve explicit precision, and every referenced evidence file exists
inside evidence/. Original bytes match their retained SHA-256 hashes. All descriptions
match their canonical source and offline extraction. Package hashes and ZIP integrity
are checked. See validation.json for numeric results and manifest.json for traceability.
"""


def main():
    if ROOT.exists():
        raise FileExistsError(f"Refusing to overwrite existing handover: {ROOT}")
    ROOT.mkdir(parents=True)
    canonical = json.loads((DATA / "historical-results.json").read_text())
    subset = {r["version_key"] for r in json.loads((DATA / "target-comparison-compact.json").read_text())}
    assert subset <= {r["version_key"] for r in canonical}
    groups = {r["posting_key"]: r for r in json.loads((DATA / "postings.json").read_text())}
    request_lines = (DATA / "requests.jsonl").read_bytes().splitlines(keepends=True)
    requests = {json.loads(line)["request_key"]: json.loads(line) for line in request_lines}
    needed_requests = set()
    records, mappings = [], []
    for row in canonical:
        for observation in row["evidence"]:
            request = requests[observation["request_key"]]
            raw = (DATA / observation["source_artifact"]).read_bytes()
            assert sha256(raw) == observation["source_sha256"] == request["sha256"]
            files, payload = retain_body(raw, request)
            native = native_record(request, raw)
            original = request["requested_url"].split("id_/", 1)[-1]
            parsed = native[0] if native else extract(raw, original)
            assert parsed and parsed["description"] == row["description"]
            result = make_record(row, observation, request, parsed, files,
                                 source_entry(payload, parsed), groups, subset)
            records.append(result)
            mappings.append({
                "source_record_id": result["source_record_id"], "version_key": row["version_key"],
                "posting_key": row["posting_key"], "request_key": observation["request_key"],
                "comparison_subset": row["version_key"] in subset,
                "source_url": observation["source_url"],
                "original_evidence_files": [files[0]],
                "original_sha256": observation["source_sha256"],
                "description_sha256": sha256(result["description"].encode("utf-8")),
                "verified_archive_capture_at": observation.get("archive_capture_at")
                if observation.get("archive_timestamp_verified") else None,
                "source_declared_dates": parsed.get("source_declared_dates", {}),
                "extraction_selector": parsed["extraction_selector"],
                "canonical_review_status": row["review_status"],
            })
            needed_requests.add(observation["request_key"])
            if observation.get("warc_evidence"):
                needed_requests.add(observation["warc_evidence"]["index_request_key"])
    evidence = ROOT / "evidence/collection"
    evidence.mkdir(parents=True)
    for filename in ["historical-results.json", "postings.json", "target-comparison-compact.json"]:
        shutil.copyfile(DATA / filename, evidence / filename)
    (evidence / "requests.jsonl").write_bytes(b"".join(
        line for line in request_lines if json.loads(line)["request_key"] in needed_requests
    ))
    extraction = ROOT / "evidence/extraction-code"
    extraction.mkdir(parents=True)
    for filename in ["phase0.py", "reprocess.py", "recover_commoncrawl.py", "objective_audit.py"]:
        shutil.copyfile(Path(__file__).parent / filename, extraction / filename)
    shutil.copyfile(DATA.parent.parent / "requirements-research-lock.txt",
                    extraction / "requirements-research-lock.txt")
    (ROOT / "historical-postings.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    stats = statistics(records, mappings)
    (ROOT / "README.md").write_text(readme(stats), encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("validate_handover.py"), ROOT / "validate.py")
    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "statistics": stats, "records": mappings,
        "canonical_input_sha256": sha256((DATA / "historical-results.json").read_bytes()),
        "request_log_selection": "Exact original lines for exported request_keys and WARC index evidence.",
        "files_sha256": {
            str(p.relative_to(ROOT)): sha256(p.read_bytes())
            for p in sorted(ROOT.rglob("*")) if p.is_file()
        },
    }
    write_json(ROOT / "manifest.json", manifest)
    from validate_handover import validate
    validation = validate(ROOT)
    validation.update(stats)
    validation["offline_source_description_matches"] = len(records)
    write_json(ROOT / "validation.json", validation)
    destination = ROOT.parent / "historical-postings-handover.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file():
                archive.write(path, str(path.relative_to(ROOT)))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()
        }
    print(json.dumps({"zip": str(destination), "zip_sha256": sha256(destination.read_bytes()),
                      "zip_bytes": destination.stat().st_size, **validation}, indent=2))


if __name__ == "__main__":
    main()
