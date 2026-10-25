"""Offline checks against manually reviewed legacy source expectations.

These are development cases, not an independent estimate of population recall.
Expected titles were checked against source headings, not inferred from URLs.
"""

import json
import re

from phase0 import DATA, archive_evidence, atomic_json, digest, extract

EXPECTED = [
    ("6036628", "Full Time Teller Beacon Mall", "766385"),
    ("3565822", "Design Thinking Manager Capital One Labs", None),
    ("3814101", "Vice President Senior Product Manager Wire Payments Treasury Management", None),
    ("3779801", "Commercial Card Product Manager", None),
    ("3833762", "Senior Vice President Relationship Manager V (McLean VA)", None),
    ("4147338", "Senior Administrative Support Assistant (Mclean VA)", None),
    ("3743579", "Senior Business Banker Dallas\\Fort Worth Tx", None),
    ("3898459", "AVP Process Management Loan and Derivative Operations McLean", None),
    ("4114848", "Treasury Management Sales Specialist Business Banking & Government", None),
    ("4137640", "Sr. Director Customer Relationship Management", None),
    ("4354670", "Application Developer Sr (AI)", None),
    ("3974801", "Business Analyst (Analyst Development Program) Dartmouth College", None),
    ("3974819", "Business Analyst (Analyst Development Program) Smith College", None),
    ("3974800", "Business Analyst (Analyst Development Program) MIT", None),
    ("4461538", "Part Time Work At Home Customer Service Specialist", None),
    ("4114850", "Head of Product Capital One Labs", None),
    ("4656884", "Brand Marketing Intern", None),
    ("4702072", "Director HR Client Consulting (USA)", None),
    ("3974818", "Business Analyst (Analyst Development Program) Johns Hopkins University", None),
    ("4687862", "Capital One Labs iOS Developer (AI)", None),
    ("4753278", "Capital One Labs Applied Application Architect", None),
    ("5200443", "Part Time Work at Home Customer Service Specialist", None),
    ("5209369", "Full Time Work at Home Customer Service Specialist", None),
    ("4981857", "Senior Digital Product Manager", None),
    ("5333957", "Full TIme Work at Home Customer Service Coordinator", None),
    ("5346091", "Design Strategist Learning Experience Team Capital One Labs", None),
    ("5240773", "Sr. Risk Representative", "755810"),
    ("5352776", "Part Time Work At Home Customer Service Associate", "757297"),
    ("5352774", "Part Time Work at Home Customer Service Specialist", "757284"),
    ("5453011", "Full Time Work at Home Customer Service Specialist", "758865"),
]


def main():
    requests = {r["request_key"]: r for r in map(json.loads, (DATA / "requests.jsonl").read_text().splitlines())}
    by_id = {}
    for item in requests.values():
        if "/web/" not in item["requested_url"]:
            continue
        match = re.search(r"/jobid(\d+)", item["requested_url"])
        if match:
            by_id.setdefault(match[1], item)
    manifest = []
    for native_id, title, reference in EXPECTED:
        item = by_id.get(native_id)
        if item is None:
            manifest.append(dict(native_id=native_id, expected_title=title, passed=False, failure="missing source"))
            continue
        body = (DATA / item["artifact_path"]).read_bytes()
        original = item["requested_url"].split("id_/", 1)[1]
        result = extract(body, original)
        checks = dict(source_hash=digest(body) == item["sha256"], description_present=bool(result),
                      title=result is not None and result["title"] == title,
                      source_sections=result is not None and "Qualifications" in result["description"],
                      no_related_jobs=result is not None and "Similar Jobs" not in result["description"],
                      reference=reference is None or result is not None and result["identifiers"].get("reference_code") == reference,
                      archive_verification=bool(archive_evidence({**item,"original_url":original})) == (native_id != "4114848"))
        manifest.append(dict(native_id=native_id, original_url=original, request_key=item["request_key"],
                             artifact_path=item["artifact_path"], sha256=item["sha256"], expected_title=title,
                             expected_reference=reference, expected_extraction="role description",
                             expected_selector='[itemprop="description"]', checks=checks, passed=all(checks.values()),
                             review_method="source heading, ID, description section boundaries, qualifications and replay headers compared",
                             sample_role="development"))
    atomic_json(DATA / "benchmark-manifest.json", manifest)
    metrics = dict(cases=len(manifest), passed=sum(r["passed"] for r in manifest),
                   failed=sum(not r["passed"] for r in manifest),
                   limitations="Development benchmark; all 30 cases have manually inspected surviving source text. Not population recall or an independent held-out accuracy estimate.")
    atomic_json(DATA / "benchmark-results.json", metrics)
    print(json.dumps(metrics, indent=2))
    if metrics["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
