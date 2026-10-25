"""Evidence correctness checks use small synthetic pages, not copied job text."""

import json
import gzip
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import phase0 as p


def posting(title="Analyst", identifier="R1", description=None):
    value = {"@type": "JobPosting", "title": title, "identifier": identifier,
             "hiringOrganization": {"name": "Capital One"},
             "datePosted": "2020-04-01", "description": description or (
                 "<h2>Responsibilities</h2><p>" + "Analyze risk. " * 50 +
                 "</p><h2>Basic Qualifications</h2><p>Statistics degree.</p>")}
    return ('<html lang="en"><script type="application/ld+json">' + json.dumps(value).replace("</", "<\\/") +
            '</script></html>').encode()


def evidence(timestamp="20141020122526", memento="Mon, 20 Oct 2014 12:25:26 GMT"):
    original = "http://jobs.capitalone.com:80/city/jobid1-test-jobs"
    return dict(requested_url=f"https://web.archive.org/web/{timestamp}id_/{original}",
                final_url=f"https://web.archive.org/web/{timestamp}id_/{original}",
                original_url=original, request_key="one", retrieved_at="2026-10-09T00:00:00+00:00",
                response_headers=[["memento-datetime", memento],
                                  ["link", f'<{original}>; rel="original"']])


def test_extract_preserves_sections_and_publication_date():
    result = p.extract(posting(), "https://www.capitalonecareers.com/job/a")
    assert "Responsibilities\n" in result["description"]
    assert "Basic Qualifications\n" in result["description"]
    assert result["source_declared_dates"] == {"datePosted": "2020-04-01"}


def test_stored_gzip_is_decoded_for_extraction_without_rewriting_source():
    original = gzip.compress(posting())
    result = p.extract(original, "https://www.capitalonecareers.com/job/a")
    assert result["title"] == "Analyst"
    assert original.startswith(b"\x1f\x8b")


def test_philippines_scoped_description_omits_navigation_and_does_not_date_filename():
    page = b'<nav>Other roles</nav><div id="oppor-new-div"><h1>Analyst</h1><div class="share-box">Share</div><h1>Job Summary</h1><p>Analyze data</p><h1>JOB SPECIFICATIONS/QUALIFICATIONS</h1><p>Degree</p></div><a href="https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/City/Analyst_R123/apply">Apply</a>'
    result = p.extract(page, "https://capitalonecareers.com.ph/analyst_04072026.php")
    assert result["identifiers"]["requisition_id"] == "R123"
    assert "Other roles" not in result["description"] and "Share" not in result["description"]
    assert result["source_declared_dates"] == {}


@pytest.mark.parametrize("html", [
    b"<h1>This job is no longer available</h1>",
    b'<html><div id="app"></div><script>fetch("live-data")</script></html>',
    b'<script type="application/ld+json">{broken</script>',
    b"<h1>Capital One careers</h1><p>Search our jobs</p>",
])
def test_shells_expired_pages_and_malformed_data_are_not_descriptions(html):
    assert p.extract(html, "https://www.capitalonecareers.com/job/a") is None


def test_unrelated_company_structured_data_is_rejected():
    assert p.extract(posting().replace(b"Capital One", b"Another Company"),
                     "https://www.capitalonecareers.com/job/a") is None


def test_embedded_scripts_do_not_enter_description_text():
    result = p.extract(posting(description="<p>Valid duties</p><script>BAD()</script>"),
                       "https://www.capitalonecareers.com/job/a")
    assert result["description"] == "Valid duties"


def test_jsonld_graph_and_type_list():
    data = {"@graph": [{"@type": ["JobPosting"], "title": "Analyst"}]}
    assert list(p.json_postings(data))[0]["title"] == "Analyst"


def test_official_campus_page_can_use_scoped_apply_link_when_org_is_missing():
    page = posting().decode().replace('"hiringOrganization": {"name": "Capital One"}, ', '')
    page = page.replace('<html lang="en">', '<html lang="en"><meta name="search-job-apply-url" content="https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/Test_R1/apply">')
    assert p.extract(page.encode(), "https://www.capitalonecareers.com/job/campus") is not None
    assert p.extract(page.encode(), "https://unrelated.example/job/campus") is None


def test_regional_employer_markup_error_is_reported_with_corroborating_apply_link():
    page = posting().decode().replace('"name": "Capital One"', '"name": "Posting Date:05/10/2026"')
    page = page.replace('<html lang="en">', '<html lang="en"><meta name="search-job-apply-url" content="https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/Test_R1/apply">')
    result = p.extract(page.encode(), "https://www.capitalonecareers.ca/job/test")
    assert result["source_quality_issues"]
    assert result["company_evidence"] == "official career domain and scoped Workday apply URL"


def test_legacy_description_excludes_similar_jobs_and_preserves_external_reference():
    description = "Responsibilities " + "Help customers. " * 40 + " Qualifications: High school diploma."
    page = f'<html><body><form><h1 class="job-title">Teller</h1><span itemprop="description">{description}</span><strong>Reference Code</strong> 12345 <div class="similar-jobs">Different Role</div></form></body></html>'
    result = p.extract(page.encode(), "http://jobs.capitalone.com/city/jobid99-teller-jobs")
    assert result["title"] == "Teller"
    assert "Different Role" not in result["description"]
    assert result["identifiers"]["reference_code"] == "12345"
    assert result["identifiers"]["careers_site_job_id"] == "99"


def test_archive_timestamp_requires_matching_headers_and_original():
    item = evidence()
    assert p.archive_evidence(item) == "2014-10-20T12:25:26+00:00"
    item["response_headers"][1][1] = '<http://jobs.capitalone.com/different>; rel="original"'
    assert p.archive_evidence(item) is None


def test_timestamp_drift_cannot_be_silently_accepted():
    assert p.archive_evidence(evidence(memento="Mon, 20 Oct 2014 12:25:27 GMT")) is None


def test_publication_after_capture_flags_possible_substitution_with_timezone_tolerance():
    row = dict(archive_capture_at="2020-01-01T23:30:00+00:00",source_declared_dates={"datePosted":"2020-1-3"})
    assert p.source_date_conflict(row)
    row["source_declared_dates"]["datePosted"] = "2020-1-2"
    assert not p.source_date_conflict(row)


def test_archive_request_redirected_live_is_unverified():
    item = evidence()
    item["final_url"] = "https://www.capitalonecareers.com/job/a"
    assert p.archive_evidence(item) is None


def test_rendered_archive_timestamp_is_never_verified():
    item = evidence()
    item["transport"] = "firecrawl_rendered"
    result = p.record(item, p.extract(posting(), item["original_url"]), historical=True)
    assert result["archive_capture_at"] is None
    assert not result["archive_timestamp_verified"]


def test_title_match_does_not_merge_distinct_postings():
    first, second = evidence(), evidence()
    second["original_url"] = "http://jobs.capitalone.com/city/jobid2-test-jobs"
    a = p.record(first, p.extract(posting(), first["original_url"]), historical=True)
    b = p.record(second, p.extract(posting(identifier="R2"), second["original_url"]), historical=True)
    assert a["version_key"] != b["version_key"]


def test_changed_description_creates_separate_version():
    item = evidence()
    a = p.record(item, p.extract(posting(), item["original_url"]), historical=True)
    b = p.record(item, p.extract(posting(description="Changed role duties"), item["original_url"]), historical=True)
    assert a["version_key"] != b["version_key"]
    assert b["completeness"] == "partial"


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost/", "file:///etc/passwd",
                                  "https://other-tenant.myworkdayjobs.com/", "https://user:pass@www.capitalonecareers.com/"])
def test_collection_scope_rejects_unapproved_targets(url):
    assert not p.public_url(url)


def test_collector_checkpoints_raw_bytes_and_does_not_repeat_success(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    collector = p.Collector()
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, stream=httpx.ByteStream(b"original bytes"), headers={"content-type": "text/html"})
    collector.client = httpx.Client(transport=httpx.MockTransport(handler))
    url = "https://www.capitalonecareers.com/job/test"
    item = collector.fetch(url)
    assert item["outcome"] == "ok"
    assert collector.body(item) == b"original bytes"
    assert item["sha256"] == p.digest(b"original bytes")
    collector.fetch(url)
    assert len(calls) == 1
    restarted = p.Collector()
    assert restarted.fetch(url)["request_key"] == item["request_key"]


@pytest.mark.parametrize("status,outcome", [(429,"rate_limited"),(503,"http_error"),(404,"unavailable")])
def test_http_failures_remain_explicit(tmp_path, monkeypatch, status, outcome):
    monkeypatch.setattr(p, "DATA", tmp_path)
    collector = p.Collector()
    collector.client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, stream=httpx.ByteStream(b"failure"), headers={"retry-after": "60"})))
    item = collector.fetch("https://www.capitalonecareers.com/job/test")
    assert item["outcome"] == outcome
    assert dict(item["response_headers"])["retry-after"] == "60"
    assert "closure_reason" not in item


def test_cdx_empty_results_differ_from_unparseable_response():
    assert p.cdx_rows(b"[]") == []
    assert p.cdx_rows(b"<h1>503</h1>") is None


def test_timeout_cannot_become_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    collector = p.Collector()
    def fail(request):
        raise httpx.ReadTimeout("source did not respond")
    collector.client = httpx.Client(transport=httpx.MockTransport(fail))
    assert collector.fetch("https://www.capitalonecareers.com/job/test")["outcome"] == "timeout"


def test_ignored_range_does_not_download_entire_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    collector = p.Collector()
    collector.client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=httpx.ByteStream(b"whole archive"))))
    item = collector.fetch("https://data.commoncrawl.org/test.warc.gz", headers={"Range": "bytes=10-19"})
    assert item["outcome"] == "range_rejected"
    assert item["bytes"] == 0


def test_request_budget_stops_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    collector = p.Collector(max_requests=0)
    with pytest.raises(p.BudgetExceeded):
        collector.fetch("https://www.capitalonecareers.com/job/test")


@pytest.mark.parametrize("url", ["https://web.archive.org/web/20200101000000id_/http://jobs.capitalone.com/jobid1",
                                 "https://www.aeaweb.org/joe/archive/listing.php?JOE_ID=201312_399328"])
def test_historical_cap_includes_archives_and_surviving_copies(tmp_path, monkeypatch, url):
    monkeypatch.setattr(p,"DATA",tmp_path)
    collector = p.Collector(max_historical_payloads=0)
    with pytest.raises(p.BudgetExceeded):
        collector.fetch(url)


def test_export_is_idempotent_without_discarding_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    item = evidence()
    a = p.record(item, p.extract(posting(), item["original_url"]), historical=True)
    b = p.record(item, p.extract(posting(description="Different"), item["original_url"]), historical=True)
    assert len(p.export([a,a,b])) == 2
    assert len(json.loads((tmp_path / "results.json").read_text())) == 2


def test_export_retains_multiple_evidence_observations_and_nullable_original(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    item = evidence()
    a = p.record(item, p.extract(posting(), item["original_url"]), historical=True)
    b = {**a, "request_key": "second", "source_url": "https://web.archive.org/web/other"}
    copy = {**a, "version_key": "copy", "original_url": None, "request_key": "third"}
    rows = p.export([a, b, copy])
    assert len(rows) == 2
    merged = next(r for r in rows if r["original_url"])
    assert {e["request_key"] for e in merged["evidence"]} == {"one", "second"}


def test_broken_pagination_is_checkpointed_as_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", tmp_path)
    class Stub:
        def fetch(self, url):
            return dict(request_key="page", requested_url=url, outcome="ok")
        def body(self, item):
            return b'<section id="search-results" data-current-page="1" data-total-pages="2" data-total-results="1"></section>'
    p.current(Stub())
    inventory = json.loads((tmp_path / "current-inventory.json").read_text())
    assert inventory["pagination_complete"] is False
