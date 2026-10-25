"""Capital One Phase 0 research harness; not the proposed engine or its CLI.

Run from the repository root. Raw HTTP bodies and request metadata are retained
before extraction. Successful responses are reused when a collection resumes.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlencode, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/capital-one"
ALLOWED = {
    "www.capitalonecareers.com", "capitalonecareers.com", "jobs.capitalone.com",
    "www.capitalonecareers.ca", "capitalonecareers.ca", "jobs.capitalone.co.uk",
    "capitalonecareers.com.ph", "www.capitalonecareers.com.ph",
    "capitalone.wd12.myworkdayjobs.com", "capitalone.wd1.myworkdayjobs.com",
    "cscapitalone.taleo.net", "capitalone.taleo.net", "www.capitalone-campus.com",
    "web.archive.org", "archive.org", "index.commoncrawl.org",
    "data.commoncrawl.org", "www.aeaweb.org", "aeaweb.org",
    "cse.sc.edu", "www.cse.sc.edu", "sciences.ucf.edu", "www.capitalone.com",
}
USER_AGENT = "ArchvivePhase0/0.1 (public Capital One job preservation research)"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes):
    return hashlib.sha256(value).hexdigest()


def source_date_conflict(row):
    raw = row.get("source_declared_dates", {}).get("datePosted", "")
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:T|$)", str(raw))
    capture = row.get("archive_capture_at")
    if not match or not capture:
        return False
    try:
        # Allow a calendar day for a publisher's unspecified local timezone.
        return (date(*map(int,match.groups()))-date.fromisoformat(capture[:10])).days>1
    except ValueError:
        return False


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def soup(body: bytes):
    # Some archive replays send stored gzip despite Accept-Encoding: identity.
    # Keep transport bytes intact; bound the derived representation separately.
    if body.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
            body = compressed.read(16 * 1024**2 + 1)
        if len(body) > 16 * 1024**2:
            raise ValueError("Decoded representation exceeds 16 MiB")
    return BeautifulSoup(body, "lxml")


def text_content(node):
    # Preserve section and list boundaries, without executing archived scripts.
    node = BeautifulSoup(str(node), "lxml")
    for tag in node.select("script,style,nav"):
        tag.decompose()
    return "\n".join(x.strip() for x in node.get_text("\n").splitlines() if x.strip())


def public_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED
            and not parsed.username and not parsed.password
            and parsed.port in {None, 80, 443})


def historical_payload(url):
    parsed = urlsplit(url)
    return ((parsed.hostname == "web.archive.org" and parsed.path.startswith("/web/"))
            or parsed.hostname == "data.commoncrawl.org"
            or (parsed.hostname in {"www.aeaweb.org","aeaweb.org"} and "JOE_ID=" in parsed.query)
            or (parsed.hostname in {"cse.sc.edu","www.cse.sc.edu"} and parsed.path.startswith("/job/"))
            or (parsed.hostname == "sciences.ucf.edu" and "Capital-One-" in parsed.path and parsed.path.endswith(".pdf")))


class BudgetExceeded(RuntimeError):
    pass


class Collector:
    def __init__(self, max_requests=3000, max_bytes=1024**3, retry_failed=False, max_historical_payloads=None):
        self.directory = DATA / "artifacts"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.host_locks = {host: threading.Lock() for host in ALLOWED}
        self.last_request = {}
        self.requests = {}
        self.attempts = 0
        self.downloaded = 0
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.retry_failed = retry_failed
        amendment = DATA / "scope-amendment.json"
        default_historical_limit = json.loads(amendment.read_text())["historical_payload_limit"] if amendment.exists() else 200
        self.max_historical_payloads = default_historical_limit if max_historical_payloads is None else max_historical_payloads
        self.historical_attempts = 0
        self.started = time.monotonic()
        self.client = httpx.Client(timeout=25, follow_redirects=False,
                                   headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        manifest = DATA / "requests.jsonl"
        if manifest.exists():
            for line in manifest.read_text().splitlines():
                item = json.loads(line)
                self.requests[item["request_key"]] = item
                self.attempts += 1
                self.downloaded += item.get("bytes", 0)
                self.historical_attempts += int(historical_payload(item["requested_url"]))

    def _save(self, item, body=b""):
        with self.lock:
            if item.get("imported_existing_probe"):
                self.attempts += 1
                self.downloaded += len(body)
                self.historical_attempts += int(historical_payload(item["requested_url"]))
            if body:
                name = digest(body) + ".bin"
                path = self.directory / name
                if not path.exists():
                    tmp = path.with_suffix(".tmp")
                    tmp.write_bytes(body)
                    tmp.replace(path)
                item.update(artifact_path=str(path.relative_to(DATA)),
                            sha256=digest(body), bytes=len(body))
            self.requests[item["request_key"]] = item
            with (DATA / "requests.jsonl").open("a") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def body(self, item):
        return (DATA / item["artifact_path"]).read_bytes() if item.get("artifact_path") else b""

    def fetch(self, url, *, method="GET", payload=None, headers=None):
        if not public_url(url):
            raise ValueError(f"Source outside approved public domains: {url}")
        key = digest(json.dumps([method, url, payload, headers], sort_keys=True).encode())
        cached = self.requests.get(key)
        if cached and (cached.get("outcome") == "ok" or not self.retry_failed):
            return cached
        with self.lock:
            if historical_payload(url):
                if self.historical_attempts >= self.max_historical_payloads:
                    raise BudgetExceeded("Historical payload budget exhausted (including recruiting copies)")
                self.historical_attempts += 1
        host = urlsplit(url).hostname
        with self.host_locks[host]:
            delay = 1.5 if host in {"web.archive.org", "index.commoncrawl.org"} else 0.25
            time.sleep(max(0, self.last_request.get(host, 0) + delay - time.monotonic()))
            item = dict(request_key=key, requested_url=url, method=method,
                        request_body=payload, request_headers=headers or {},
                        retrieved_at=now(), transport="direct_http", redirects=[], bytes=0)
            current = url
            try:
                for _ in range(6):
                    with self.lock:
                        if (self.attempts >= self.max_requests or self.downloaded >= self.max_bytes
                                or time.monotonic() - self.started > 2 * 8 * 3600):
                            raise BudgetExceeded("Request, byte, or working-time budget exhausted")
                        self.attempts += 1
                    if not public_url(current):
                        raise ValueError(f"Rejected redirect: {current}")
                    # A redirected host must be fetched independently to preserve host serialization.
                    if urlsplit(current).hostname != host:
                        item.update(outcome="redirect_requires_separate_request", final_url=current)
                        return self._save(item)
                    with self.client.stream(method, current, json=payload, headers=headers) as response:
                        if headers and "Range" in headers:
                            wanted = re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"])
                            actual = re.fullmatch(r"bytes (\d+)-(\d+)/\d+", response.headers.get("content-range", ""))
                            if response.status_code != 206 or not actual or not wanted or actual.groups() != wanted.groups():
                                item.update(final_url=str(response.url), status=response.status_code,
                                            response_headers=list(response.headers.multi_items()),
                                            outcome="range_rejected")
                                return self._save(item)
                        chunks = []
                        for chunk in response.iter_raw():
                            with self.lock:
                                if self.downloaded + len(chunk) > self.max_bytes:
                                    raise BudgetExceeded("Byte budget exhausted")
                                self.downloaded += len(chunk)
                            chunks.append(chunk)
                        body = b"".join(chunks)
                        item.update(final_url=str(response.url), status=response.status_code,
                                    response_headers=list(response.headers.multi_items()),
                                    retrieved_at=now(), elapsed_seconds=round(response.elapsed.total_seconds(), 3))
                        # Request identity bytes, so retained bytes can be parsed offline as received.
                        if response.is_redirect:
                            destination = urljoin(current, response.headers.get("location", ""))
                            item["redirects"].append(dict(url=current, status=response.status_code,
                                                         location=destination,
                                                         headers=list(response.headers.multi_items()),
                                                         sha256=digest(body)))
                            current = destination
                            continue
                        item["outcome"] = ("ok" if response.status_code == 200 or response.status_code == 206
                                           else "rate_limited" if response.status_code == 429
                                           else "unavailable" if response.status_code in {404, 410}
                                           else "blocked" if response.status_code in {401, 403}
                                           else "http_error")
                        return self._save(item, body)
                item["outcome"] = "redirect_limit"
            except BudgetExceeded:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                item.update(outcome="timeout" if isinstance(exc, httpx.TimeoutException) else "network_error",
                            error=f"{type(exc).__name__}: {exc}", final_url=current)
            finally:
                self.last_request[host] = time.monotonic()
            return self._save(item)


def archive_evidence(item):
    headers = dict(item.get("response_headers", []))
    memento = headers.get("memento-datetime")
    final = item.get("final_url", "")
    match = re.search(r"/web/(\d{14})(?:id_)?/(.+)", final)
    links = headers.get("link", "")
    original_link = re.search(r'<([^>]+)>;\s*rel="original"', links)
    if not (memento and match and original_link and urlsplit(final).hostname == "web.archive.org"):
        return None
    def identity(url):
        parsed = urlsplit(url)
        return parsed.hostname, unquote(parsed.path), parsed.query
    expected_original = item.get("original_url", match[2])
    if identity(original_link[1]) != identity(expected_original):
        return None
    try:
        timestamp = parsedate_to_datetime(memento).astimezone(timezone.utc)
        expected = datetime.strptime(match[1], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if timestamp != expected:
        return None
    return timestamp.isoformat()


def json_postings(node):
    if isinstance(node, list):
        for child in node:
            yield from json_postings(child)
    if isinstance(node, dict):
        kind = node.get("@type", [])
        if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
            yield node
        if "@graph" in node:
            yield from json_postings(node["@graph"])


def extract(body, url):
    document = soup(body)
    if urlsplit(url).hostname in {"capitalonecareers.com.ph", "www.capitalonecareers.com.ph"}:
        box = document.select_one("#oppor-new-div")
        title = box.find("h1") if box else None
        apply = next((a["href"] for a in document.select('a[href]')
                      if urlsplit(a["href"]).hostname == "capitalone.wd12.myworkdayjobs.com"
                      and "/Capital_One/job/" in a["href"]), None)
        if box and title and apply:
            for tag in box.select(".share-box, .col-md-12, script, style"):
                tag.decompose()
            text = text_content(box)
            if "Job Summary" in text and "QUALIFICATIONS" in text:
                req = re.search(r"_(R\d+)/apply", apply)
                return dict(title=title.get_text(" ", strip=True), description=text,
                            description_html=str(box), identifiers={"requisition_id": req[1] if req else None},
                            source_declared_dates={}, location="Philippines", language="en",
                            extraction_selector="#oppor-new-div excluding navigation and sharing controls",
                            extraction_kind="philippines_official", company_evidence="official regional board and scoped Workday apply link")
    for script in document.select('script[type="application/ld+json"]'):
        try:
            entries = list(json_postings(json.loads(script.get_text())))
        except (ValueError, TypeError):
            continue
        for entry in entries:
            org = entry.get("hiringOrganization", {})
            apply_meta = document.select_one('meta[name="search-job-apply-url"]')
            apply_url = apply_meta.get("content", "") if apply_meta else ""
            official_scoped_apply = (
                urlsplit(url).hostname in {"www.capitalonecareers.com", "www.capitalonecareers.ca", "jobs.capitalone.co.uk"}
                and urlsplit(apply_url).hostname in {"capitalone.wd12.myworkdayjobs.com", "capitalone.wd1.myworkdayjobs.com"}
                and "/Capital_One/" in apply_url)
            malformed_regional_org = bool(re.fullmatch(r"Posting Date:.*", org.get("name", ""))) if isinstance(org, dict) else False
            if "capital one" not in json.dumps(org).lower() and not (
                    official_scoped_apply and (not org or malformed_regional_org)):
                continue
            description = entry.get("description", "")
            if not description:
                continue
            req = document.select_one('meta[name="job-ats-req-id"]')
            identifier = entry.get("identifier")
            return dict(title=entry.get("title"), description_html=description,
                        description=text_content(description), source_declared_dates={
                            k: entry[k] for k in ("datePosted", "validThrough", "dateModified") if entry.get(k)},
                        identifiers={"structured_identifier": identifier,
                                     "requisition_id": req.get("content") if req else None},
                        location=entry.get("jobLocation"), language=document.html.get("lang") if document.html else None,
                        extraction_selector='script[type="application/ld+json"] -> JobPosting.description',
                        extraction_kind="jobposting_jsonld",
                        company_evidence="official career domain and scoped Workday apply URL" if official_scoped_apply else "JobPosting.hiringOrganization",
                        source_quality_issues=["hiringOrganization.name contains a posting date"] if malformed_regional_org else [])
    # Legacy TMP detail pages have an isolated premierBox; never extract the search form.
    box = document.select_one('[itemprop="description"]') or document.select_one(".jobDesc")
    if box is None and urlsplit(url).hostname in {"www.capitalonecareers.com", "www.capitalonecareers.ca", "jobs.capitalone.co.uk"}:
        candidate = document.select_one(".ats-description")
        if candidate and "Capital One" in candidate.get_text():
            box = candidate
    if box and re.search(r"qualifications", box.get_text(), re.I):
        selector = ('[itemprop="description"]' if box.get("itemprop") == "description"
                    else ".ats-description" if "ats-description" in box.get("class", []) else ".jobDesc")
        for tag in box.select("form,script,style,.share,.apply"):
            tag.decompose()
        title = document.select_one('#Job_JobTitle, .job-title, [itemprop="title"], .job-description__intro h1, .ajd-job-title h1, .ajd-job-title h2')
        if title is None and document.select_one(".jobDesc"):
            title = document.find("h2")
        if title is None:
            og_title = document.select_one('meta[property="og:title"]')
            headings = [h for h in document.find_all("h1") if h.get_text(strip=True)]
            if og_title:
                title = next((h for h in headings if og_title.get("content", "").startswith(h.get_text(" ", strip=True))), None)
            if title is None and len(headings) == 1:
                title = headings[0]
        text = text_content(box)
        if len(text) < 500:
            return None
        page_text = text_content(document)
        ref = re.search(r"Reference Code\s*[:\n ]*([\w-]+)", page_text)
        apply_id = re.search(r"[?&]job=(\d+)", str(document))
        site_id = re.search(r"/jobid(\d+)", url)
        loc = re.search(r"(?:Primary Location|Job Location|Location)[:\s]+([^\n]+)", page_text)
        structured_dates = {}
        structured_id = None
        for script in document.select('script[type="application/ld+json"]'):
            try:
                entries = list(json_postings(json.loads(script.get_text())))
            except (ValueError, TypeError):
                continue
            for entry in entries:
                if title and entry.get("title") == title.get_text(" ", strip=True):
                    structured_dates = {k:entry[k] for k in ["datePosted","validThrough","dateModified"] if entry.get(k)}
                    structured_id = entry.get("identifier")
        return dict(title=title.get_text(" ", strip=True) if title else None,
                    description_html=str(box), description=text,
                    source_declared_dates=structured_dates, identifiers={
                        "reference_code": ref[1] if ref else apply_id[1] if apply_id else None,
                        "careers_site_job_id": site_id[1] if site_id else None,
                        "structured_identifier": structured_id},
                    location=loc[1] if loc else None, language="en",
                    extraction_selector=selector, extraction_kind="official_html" if selector == ".ats-description" else "legacy_tmp")
    # AEA and USC are attributable recruiting copies, not official archive captures.
    if urlsplit(url).hostname in {"www.aeaweb.org", "aeaweb.org"}:
        text = text_content(document)
        if "Full Text of JOE Listing:" not in text or "Capital One" not in text:
            return None
        description = text.split("Full Text of JOE Listing:", 1)[1].split("Application Instructions:", 1)[0].strip()
        title = re.search(r"Title:\s*([^\n]+)", text)
        issue = re.search(r"JOE - ([A-Za-z]+ \d{4})", text)
        original = re.search(r'https?://(?:cs)?capitalone\.taleo\.net/[^\s<>]*?job=\d+', text)
        return dict(title=title[1] if title else None, description=description,
                    description_html=None, identifiers={"joe_id": url.split("JOE_ID=")[-1]},
                    attributed_original_url=original[0] if original else None,
                    source_declared_dates={"issue": issue[1] if issue else None}, location=None, language="en",
                    extraction_selector="Full Text of JOE Listing through Application Instructions",
                    extraction_kind="aea_recruiting_copy")
    article = document.select_one("article")
    if urlsplit(url).hostname in {"cse.sc.edu", "www.cse.sc.edu"} and article:
        field = article.select_one('.field--name-body')
        title_text = text_content(field).splitlines()[0] if field else None
        text = text_content(article)
        if "Capital One" in text and "Qualifications" in text:
            date = re.search(r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}", text)
            original = next((a["href"] for a in article.select('a[href]')
                             if urlsplit(a["href"]).hostname == "cscapitalone.taleo.net" and "job=" in a["href"]), None)
            native_id = re.search(r"[?&]job=(\d+)", original or "")
            return dict(title=title_text,
                        description=text, description_html=str(article), identifiers={"reference_code": native_id[1] if native_id else None},
                        attributed_original_url=original,
                        source_declared_dates={"copy_publication": date[0] if date else None},
                        location=None, language="en", extraction_selector="article",
                        extraction_kind="university_recruiting_copy")
    return None


def record(item, extracted, *, historical=False):
    original = item.get("original_url", item["requested_url"])
    capture = archive_evidence(item)
    rendered = item.get("transport") == "firecrawl_rendered"
    result = dict(company="Capital One", original_url=original, source_url=item["requested_url"],
                  retrieved_at=item["retrieved_at"], engine_capture_at=item["retrieved_at"],
                  retrieval_time_basis=item.get("retrieval_time_basis", "UTC time after HTTP response body read"),
                  archive_capture_at=capture, archive_timestamp_verified=bool(capture),
                  requested_archive_timestamp=item.get("requested_archive_timestamp"),
                  source_type="archive_official" if historical else "live_official",
                  completeness="partial", historical=historical,
                  source_artifact=item.get("artifact_path"), source_sha256=item.get("sha256"),
                  request_key=item["request_key"], parser_version="phase0-1", **extracted)
    result["representation_decoding"] = dict(item.get("response_headers", [])).get("content-encoding", "identity")
    if extracted["extraction_kind"] in {"aea_recruiting_copy", "university_recruiting_copy", "university_pdf"}:
        result["source_type"] = "attributable_copy"
        result["historical"] = True
        result["original_url"] = extracted.get("attributed_original_url")
    detail_id = re.search(r"/job/.*?/\d+/(\d+)(?:$|[/?])", urlsplit(result["original_url"] or "").path)
    if detail_id:
        result["identifiers"]["careers_site_job_id"] = detail_id[1]
    result["source_date_evidence"] = []
    for name, value in result.get("source_declared_dates", {}).items():
        if value is None:
            continue
        precision = "unparsed"
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", str(value)):
            precision = "calendar_day"
        elif re.fullmatch(r"[A-Za-z]+ \d{4}", str(value)):
            precision = "calendar_month"
        elif re.fullmatch(r"[A-Za-z]+ \d{1,2}, \d{4}", str(value)):
            precision = "calendar_day"
        elif re.match(r"\d{4}-\d{2}-\d{2}T", str(value)):
            precision = "timestamp_as_declared"
        result["source_date_evidence"].append(dict(field=name, raw=value, precision=precision,
                                                   attributed_to=result["source_url"]))
    text = result["description"]
    # Full claims are conservative and remain subject to manual source comparison.
    if (("Qualifications" in text or "qualifications" in text) and
            ("Responsibilities" in text or "What You" in text or "responsible" in text or "Basic Qualifications" in text)
            and len(text) > 500):
        result["completeness"] = "full"
    result["identity_confidence"] = "supported"
    host = urlsplit(original).hostname
    if host == "www.capitalonecareers.ca":
        result["board_region"] = "Canada"
    elif host == "jobs.capitalone.co.uk":
        result["board_region"] = "United Kingdom"
    elif host in {"capitalonecareers.com.ph", "www.capitalonecareers.com.ph"}:
        result["board_region"] = "Philippines"
    result["review_status"] = "needs_review"
    if rendered and historical:
        result["archive_timestamp_verified"] = False
        result["archive_capture_at"] = None
    result["content_hash"] = digest(text.encode())
    identity_url = result["original_url"] or result["source_url"]
    result["version_key"] = digest(json.dumps([identity_url, result.get("language"), result["content_hash"]]).encode())
    return result


def export(records, stem="results"):
    unique = {}
    for row in records:
        primary = dict(
            request_key=row["request_key"], source_url=row["source_url"],
            retrieved_at=row["retrieved_at"], source_artifact=row.get("source_artifact"),
            source_sha256=row.get("source_sha256"), archive_capture_at=row.get("archive_capture_at"),
            archive_timestamp_verified=row.get("archive_timestamp_verified", False),
            source_type=row.get("source_type"), extraction_kind=row.get("extraction_kind"),
            retrieval_time_basis=row.get("retrieval_time_basis"), warc_evidence=row.get("warc_evidence"))
        evidence_by_key = {e["request_key"]:e for e in row.get("evidence", [])}
        evidence_by_key[row["request_key"]] = {**evidence_by_key.get(row["request_key"], {}), **primary}
        evidence = list(evidence_by_key.values())
        if row["version_key"] not in unique:
            unique[row["version_key"]] = {**row, "evidence": []}
        target = unique[row["version_key"]]
        all_evidence = {e["request_key"]:e for e in target["evidence"]}
        all_evidence.update({e["request_key"]:e for e in evidence})
        target["evidence"] = list(all_evidence.values())
        # Prefer a verified replay as the representative observation for identical text.
        if row.get("archive_timestamp_verified") and not target.get("archive_timestamp_verified"):
            unique[row["version_key"]] = {**row, "evidence": target["evidence"]}
    records = sorted(unique.values(), key=lambda r: (r["original_url"] or r["source_url"], r["version_key"]))
    atomic_json(DATA / f"{stem}.json", records)
    fields = ["title", "original_url", "source_url", "source_type", "historical", "completeness",
              "identifiers", "location", "language", "source_declared_dates", "archive_capture_at",
              "archive_timestamp_verified", "engine_capture_at", "retrieved_at", "source_artifact",
              "content_hash", "version_key", "review_status", "evidence", "comparison_year",
              "comparison_family", "comparison_region", "comparison_year_basis", "source_date_evidence", "description"]
    path = DATA / f"{stem}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items() if k in fields})
    return records


def existing_records():
    path = DATA / "results.json"
    return json.loads(path.read_text()) if path.exists() else []


def cdx_rows(body):
    try:
        rows = json.loads(body)
        if not rows:
            return []
        return [dict(zip(rows[0], row)) for row in rows[1:] if isinstance(row, list)]
    except (ValueError, TypeError, IndexError):
        return None


def cdx_url(pattern, start, end, limit=2000):
    return "https://web.archive.org/cdx/search/cdx?" + urlencode({
        "url": pattern, "output": "json", "from": start, "to": end,
        "filter": "mimetype:text/html", "limit": limit,
        "fl": "timestamp,original,statuscode,mimetype,digest",
    })


def is_detail(url):
    path = urlsplit(url).path.lower()
    return (bool(re.search(r"/jobid\d+", path)) or "/job/" in path
            or ("jobdetail.ftl" in path and "job=" in url)) and not path.endswith("/culture")


def copies(collector, records):
    urls = ["https://www.aeaweb.org/joe/archive/listing.php?JOE_ID=" + key
            for key in ["201312_399327", "201312_399328", "201312_399798"]]
    urls.append("https://cse.sc.edu/job/capital-one-it-development-program")
    for url in urls:
        item = collector.fetch(url)
        extracted = extract(collector.body(item), url) if item["outcome"] == "ok" else None
        if extracted:
            records.append(record(item, extracted))
    from pypdf import PdfReader
    for name, native_id in [("Statistician-Analyst-Development-Program", "749588"),
                            ("Statistician-Intern-Analyst-Internship-Program", "749814")]:
        url = f"https://sciences.ucf.edu/statistics/dms/wp-content/uploads/sites/8/2014/01/Capital-One-{name}-{native_id}.pdf"
        item = collector.fetch(url)
        if item["outcome"] != "ok":
            continue
        try:
            document = PdfReader(io.BytesIO(collector.body(item)))
            text = "\n".join(page.extract_text() for page in document.pages)
        except Exception as exc:
            print(f"PDF extraction failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        extracted = dict(title=text.splitlines()[0], description=text, description_html=None,
                         attributed_original_url=f"https://cscapitalone.taleo.net/careersection/usx/jobdetail.ftl?lang=en&job={native_id}",
                         identifiers={"reference_code": native_id}, location=None, language="en",
                         source_declared_dates={}, extraction_selector="PDF pages 1–2",
                         extraction_kind="university_pdf")
        records.append(record(item, extracted))
    export(records, "historical-results")


def regional(collector):
    results = []
    for url in ["https://www.capitalonecareers.ca/", "https://jobs.capitalone.co.uk/",
                "https://capitalonecareers.com.ph/career-opportunities.php",
                "https://capitalone.wd12.myworkdayjobs.com/Capital_One",
                "https://www.capitalonecareers.com/robots.txt",
                "https://jobs.capitalone.com/robots.txt",
                "https://www.capitalonecareers.ca/robots.txt",
                "https://jobs.capitalone.co.uk/robots.txt"]:
        item = collector.fetch(url)
        document = soup(collector.body(item))
        links = list(dict.fromkeys(urljoin(url, a["href"]) for a in document.select("a[href]")
                                  if re.search(r"job|career|workday", a["href"], re.I)))
        results.append(dict(url=url, outcome=item["outcome"], status=item.get("status"),
                            request_key=item["request_key"], links=links,
                            title=document.title.get_text(strip=True) if document.title else None))
    atomic_json(DATA / "regional-probes.json", results)


def commoncrawl(collector):
    catalog = collector.fetch("https://index.commoncrawl.org/collinfo.json")
    atomic_json(DATA / "commoncrawl-catalog-observation.json", catalog)
    patterns = ["jobs.capitalone.com/*", "www.capitalonecareers.com/job/*"]
    outcomes = []
    # Serial spaced calls; representative old, intermediate, and recent collections.
    for collection, pattern in [("CC-MAIN-2014-42", patterns[0]),
                                ("CC-MAIN-2020-05", patterns[1]),
                                ("CC-MAIN-2026-39", patterns[1])]:
        url = f"https://index.commoncrawl.org/{collection}-index?" + urlencode({
            "url": pattern, "output": "json", "pageSize": 1, "page": 0})
        item = collector.fetch(url)
        rows = []
        if item["outcome"] == "ok":
            try:
                rows = [json.loads(line) for line in collector.body(item).splitlines() if line.strip()]
            except ValueError:
                pass
        outcome = dict(collection=collection, url_pattern=pattern, outcome=item["outcome"],
                       request_key=item["request_key"], index_records=rows)
        outcomes.append(outcome)
        atomic_json(DATA / "commoncrawl-probes.json", outcomes)
        # Payload retrieval is deliberately bounded to five response records per probe.
        for row in rows[:5]:
            if row.get("status") != "200" or "filename" not in row:
                continue
            offset, length = int(row["offset"]), int(row["length"])
            warc = collector.fetch("https://data.commoncrawl.org/" + row["filename"],
                                   headers={"Range": f"bytes={offset}-{offset+length-1}"})
            outcome.setdefault("payloads", []).append(dict(locator=row, request_key=warc["request_key"],
                                                           outcome=warc["outcome"]))
        atomic_json(DATA / "commoncrawl-probes.json", outcomes)


def current(collector):
    records = existing_records()
    inventory = []
    pages = []
    total_pages = 1
    page = 1
    while page <= total_pages:
        item = collector.fetch(f"https://www.capitalonecareers.com/search-jobs?p={page}")
        document = soup(collector.body(item))
        section = document.select_one("#search-results")
        state = dict(page=page, request_key=item["request_key"], outcome=item["outcome"])
        if section is None or section.get("data-current-page") != str(page):
            pages.append({**state, "outcome": "pagination_failed"})
            atomic_json(DATA / "current-inventory.json", dict(pages=pages, urls=list(dict.fromkeys(inventory)),
                        pagination_complete=False, collected_at=now()))
            break
        total_pages = int(section.get("data-total-pages", "1"))
        urls = list(dict.fromkeys(urljoin(item["requested_url"], a["href"])
                                 for a in section.select('a[href*="/job/"]')))
        state.update(reported_total=int(section["data-total-results"]), reported_pages=total_pages,
                     urls=urls)
        pages.append(state)
        inventory.extend(urls)
        atomic_json(DATA / "current-inventory.json", dict(pages=pages, urls=list(dict.fromkeys(inventory)),
                    pagination_complete=page == total_pages, collected_at=now()))
        if page % 20 == 0:
            print(f"CURRENT inventory {page}/{total_pages}; unique URLs {len(set(inventory))}", flush=True)
        page += 1
    known = {r["request_key"] for r in records}
    for i, url in enumerate(dict.fromkeys(inventory)):
        item = collector.fetch(url)
        extracted = extract(collector.body(item), url) if item["outcome"] == "ok" else None
        if extracted and item["request_key"] not in known:
            records.append(record(item, extracted))
            known.add(item["request_key"])
        if i % 50 == 0:
            export(records)
            print(f"CURRENT descriptions {i + 1}/{len(set(inventory))}; records {len(records)}", flush=True)
    export(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["current", "regional", "commoncrawl", "copies"])
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    collector = Collector(max_requests=2400 if args.operation == "current" else 3000,
                          retry_failed=args.retry_failed)
    try:
        if args.operation == "copies":
            copies(collector, [])
        else:
            globals()[args.operation](collector)
    except (BudgetExceeded, KeyboardInterrupt) as exc:
        print(f"PARTIAL: {exc}", flush=True)
    finally:
        atomic_json(DATA / "budget.json", dict(requests=collector.attempts, bytes=collector.downloaded,
                    max_requests=collector.max_requests, max_bytes=collector.max_bytes, updated_at=now()))


if __name__ == "__main__":
    main()
