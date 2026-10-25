"""Re-extract retained artifacts offline and assemble evidence-linked exports."""

import json
import io
import re
from pypdf import PdfReader

from phase0 import DATA, atomic_json, digest, export, extract, record, text_content
from recover_commoncrawl import decode_warc


def native_record(item, body):
    url = item["requested_url"]
    if "data.commoncrawl.org/" in url:
        evidence = json.loads((DATA / "commoncrawl-payload-review.json").read_text())
        return decode_warc(item,body,evidence["locator"],evidence["index_request_key"])
    if url.startswith("https://sciences.ucf.edu/") and url.endswith(".pdf"):
        text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(body)).pages)
        original = re.search(r'https?://(?:cs)?capitalone\.taleo\.net/[^\s<>]*?job=\d+',text)
        native_id = re.search(r"(\d+)\.pdf$",url)
        parsed = dict(title=text.splitlines()[0].strip(),description=text,description_html=None,
                      identifiers={"reference_code":native_id[1]},source_declared_dates={},
                      attributed_original_url=original[0] if original else None,location=None,language="en",
                      extraction_kind="university_pdf",extraction_selector="PDF pages 1–2")
        return [record(item,parsed)]
    if "/wday/cxs/" in url and item.get("method")=="GET":
        data = json.loads(body).get("jobPostingInfo")
        if not data or not data.get("jobDescription"):
            return []
        path = url.split("/Capital_One",1)[1]
        parsed = dict(title=data.get("title"),description_html=data["jobDescription"],
                      description=text_content(data["jobDescription"]),
                      identifiers={"requisition_id":data.get("jobReqId"),"workday_posting_path":path},
                      source_declared_dates={k:data[k] for k in ["startDate","endDate"] if data.get(k)},
                      location={"primary":data.get("location"),"additional":data.get("additionalLocations")},
                      language=None,extraction_kind="regional_workday",extraction_selector="$.jobPostingInfo.jobDescription")
        original = "https://capitalone.wd12.myworkdayjobs.com/en-US/Capital_One"+path
        return [record({**item,"original_url":original},parsed)]
    return None


def apply_reviews(results):
    reviews = []
    for filename in ["benchmark-manifest", "manual-review", "comparison-review"]:
        path = DATA / f"{filename}.json"
        reviews.extend(json.loads(path.read_text()) if path.exists() else [])
    reviewed = {r["request_key"]: r for r in reviews if r.get("passed")}
    for row in results:
        match = next((reviewed[e["request_key"]] for e in row["evidence"] if e["request_key"] in reviewed), None)
        if match:
            row["review_status"] = "validated"
            row["review_evidence"] = match
    return results


def main():
    requests = {}
    for line in (DATA / "requests.jsonl").read_text().splitlines():
        row = json.loads(line)
        requests[row["request_key"]] = row
    results = []
    outcomes = []
    for item in requests.values():
        url = item["requested_url"]
        if item["outcome"] != "ok" or not item.get("artifact_path"):
            continue
        if "/cdx/" in url or "index.commoncrawl.org" in url:
            continue
        body = (DATA / item["artifact_path"]).read_bytes()
        if digest(body) != item["sha256"]:
            raise ValueError(f"Artifact integrity failure: {item['artifact_path']}")
        native = native_record(item,body)
        if native is not None:
            results.extend(native)
            continue
        historical = "/web/" in url and "web.archive.org" in url
        if historical:
            stamp, original = url.split("/web/", 1)[1].split("/", 1)
            item = {**item, "original_url": original, "requested_archive_timestamp": stamp[:14]}
        else:
            original = url
        parsed = extract(body, original)
        if parsed:
            results.append(record(item, parsed, historical=historical))
        if historical or "/job/" in url or "JOE_ID=" in url:
            outcomes.append(dict(url=url, request_key=item["request_key"], extracted=bool(parsed),
                                 outcome="description_extracted" if parsed else "no_supported_description"))
    results = export(results)
    results = export(apply_reviews(results))
    atomic_json(DATA / "extraction-outcomes.json", outcomes)
    versions = {}
    for row in results:
        versions.setdefault(row["original_url"] or row["source_url"], []).append(row["version_key"])
    atomic_json(DATA / "versions.json", versions)
    print(json.dumps(dict(records=len(results), historical=sum(r["historical"] for r in results),
                          archive_verified=sum(r["archive_timestamp_verified"] for r in results),
                          current=sum(not r["historical"] for r in results)), indent=2))


if __name__ == "__main__":
    main()
