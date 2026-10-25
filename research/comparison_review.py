"""Recheck fixed expectations from the inspected 30-cell comparison core."""

import json

from phase0 import DATA, archive_evidence, atomic_json, digest, extract, record, soup
from comparison import family, us_eligible


def main():
    requests = {r["request_key"]:r for r in map(json.loads,(DATA/"requests.jsonl").read_text().splitlines())}
    reviews = []
    for expected in json.loads((DATA/"comparison-review-selection.json").read_text()):
        item = requests[expected["request_key"]]
        original = item["requested_url"].split("id_/",1)[1]
        item = {**item,"original_url":original}
        body = (DATA/item["artifact_path"]).read_bytes()
        parsed = extract(body,original)
        result = record(item,parsed,historical=True)
        document = soup(body)
        visible = [h.get_text(" ",strip=True) for h in document.select(
            'section.job-description h1,#Job_JobTitle,[itemprop="title"],.ajd-job-title h1,.ajd-job-title h2')]
        checks = dict(hash=digest(body)==expected["sha256"], title=parsed["title"]==expected["expected_title"],
                      source_heading=expected["expected_title"] in visible,
                      identifiers=all(parsed["identifiers"].get(k)==v for k,v in expected["expected_identifiers"].items() if v),
                      qualifications=expected["qualification_excerpt"] in parsed["description"],
                      capture_year=(archive_evidence(item) or "").startswith(str(expected["year"])),
                      us_region=us_eligible(result), family=family(parsed["title"])==expected["family"],
                      no_related_jobs="Related Jobs" not in parsed["description"])
        reviews.append({**expected,"checks":checks,"passed":all(checks.values()),
                        "original_url":original,"expected_extraction":"role description",
                        "review_method":"Codex inspected source headings, role IDs and qualifications; automated hash, replay evidence, region and scope checks. Development review, not blind accuracy evaluation."})
    atomic_json(DATA/"comparison-review.json",reviews)
    metrics = dict(cases=len(reviews),passed=sum(r["passed"] for r in reviews))
    atomic_json(DATA/"comparison-review-results.json",metrics)
    print(metrics)
    if metrics["cases"]!=30 or metrics["passed"]!=30:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
